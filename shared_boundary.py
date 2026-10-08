"""Opt-in shared-edge polygons for the local X-AnyLabeling installation.

Existing polygons keep their boundaries. Newly completed polygons of other
labels are clipped against them. Shapely performs the boolean operation, so
the coincident edge uses the existing polygons' exact coordinates.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable

from shapely.geometry import LineString, MultiPoint, Point, Polygon
from shapely.ops import split, unary_union
from shapely.validation import make_valid


LOG = logging.getLogger(__name__)
AREA_EPSILON = 1e-8
MAX_HOLE_SPLITS = 32
SPECIAL_LABELS = {"AUTOLABEL_OBJECT", "AUTOLABEL_ADD", "AUTOLABEL_REMOVE"}


def _polygon(points: Iterable[tuple[float, float]]) -> Polygon | None:
    points = list(points)
    if len(points) < 3:
        return None
    polygon = Polygon(points)
    if polygon.is_empty or not polygon.is_valid or polygon.area <= AREA_EPSILON:
        return None
    return polygon


def _annotation_geometry(points: Iterable[tuple[float, float]]):
    """Read a saved annotation, retaining usable area in self-crossing rings."""
    points = list(points)
    if len(points) < 3:
        return None
    polygon = Polygon(points)
    if polygon.is_empty:
        return None
    geometry = polygon if polygon.is_valid else make_valid(polygon)
    areas = _flat_polygons(geometry)
    if not areas:
        return None
    geometry = unary_union(areas)
    return geometry if geometry.area > AREA_EPSILON else None


def _flat_polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry] if geometry.area > AREA_EPSILON else []
    if hasattr(geometry, "geoms"):
        return [part for geom in geometry.geoms for part in _flat_polygons(geom)]
    return []


def _remove_holes(polygon: Polygon, depth: int = 0) -> list[Polygon]:
    """Split a polygon through each hole so Shape can store the result."""
    if not polygon.interiors:
        return [polygon]
    if depth >= MAX_HOLE_SPLITS:
        raise ValueError("too many enclosed regions to split safely")

    hole = Polygon(polygon.interiors[0])
    point = hole.representative_point()
    min_x, min_y, max_x, max_y = polygon.bounds
    margin = max(max_x - min_x, max_y - min_y, 1.0) + 1.0
    for line in (
        LineString([(point.x, min_y - margin), (point.x, max_y + margin)]),
        LineString([(min_x - margin, point.y), (max_x + margin, point.y)]),
    ):
        pieces = _flat_polygons(split(polygon, line))
        if len(pieces) > 1:
            return [
                part
                for piece in pieces
                for part in _remove_holes(piece, depth + 1)
            ]
    raise ValueError("could not represent an enclosed region as polygons")


def _rings_from_geometry(geometry) -> list[list[tuple[float, float]]]:
    pieces = [
        part
        for polygon in _flat_polygons(geometry)
        for part in _remove_holes(polygon)
    ]
    pieces.sort(key=lambda part: (-part.area, part.bounds))
    return [list(piece.exterior.coords)[:-1] for piece in pieces]


def subtract_coordinates(
    old_points: Iterable[tuple[float, float]],
    new_points: Iterable[tuple[float, float]],
) -> list[list[tuple[float, float]]] | None:
    """Return hole-free remainder rings, or None when nothing should change.

    Invalid inputs are deliberately left untouched instead of risking label
    corruption. A fully covered old shape yields an empty list.
    """
    old_polygon = _polygon(old_points)
    new_polygon = _polygon(new_points)
    if old_polygon is None or new_polygon is None:
        return None
    if old_polygon.intersection(new_polygon).area <= AREA_EPSILON:
        return None

    return _rings_from_geometry(old_polygon.difference(new_polygon))


def _points(shape) -> list[tuple[float, float]]:
    return [(point.x(), point.y()) for point in shape.points]


def straighten_vertex_span(points, start: int, end: int, *, along_forward=False):
    """Remove the shorter boundary arc between two retained vertices."""
    ring = list(points)
    closed_duplicate = len(ring) > 1 and ring[0] == ring[-1]
    if closed_duplicate:
        ring.pop()
    count = len(ring)
    if count < 4 or not (0 <= start < count and 0 <= end < count) or start == end:
        raise ValueError("需要两个不同的顶点，且原多边形至少有四个顶点")

    def middle(a, b):
        return [(a + step) % count for step in range(1, (b - a) % count)]

    def length(a, b):
        total = 0.0
        index = a
        while index != b:
            following = (index + 1) % count
            total += math.dist(ring[index], ring[following])
            index = following
        return total

    forward = middle(start, end)
    backward = middle(end, start)
    if along_forward or length(start, end) <= length(end, start):
        removed = forward
    else:
        removed = backward
    if not removed or count - len(removed) < 3:
        raise ValueError("所选两点之间没有可删除的中间顶点，或删除后不足三个顶点")
    removed_set = set(removed)
    result = [point for index, point in enumerate(ring) if index not in removed_set]
    result_polygon = Polygon(result)
    if Polygon(ring).is_valid:
        if not result_polygon.is_valid or result_polygon.area <= AREA_EPSILON:
            raise ValueError("拉直后多边形无效，未修改标注")
    else:
        # SAM contours can already contain retraced bridges or tiny loops.
        # Keep unrelated vertices untouched; reject crossings introduced by
        # the replacement chord instead of rejecting all existing defects.
        chord = LineString([ring[start], ring[end]])
        endpoints = MultiPoint([ring[start], ring[end]])
        for index, point in enumerate(result):
            following = result[(index + 1) % len(result)]
            if (point == ring[start] and following == ring[end]) or (
                point == ring[end] and following == ring[start]
            ):
                continue
            intersection = chord.intersection(LineString([point, following]))
            if not intersection.difference(endpoints).is_empty:
                raise ValueError("新直线会与其他边界相交，请重新选择两个端点")
        if _annotation_geometry(result) is None:
            raise ValueError("拉直后没有可用的多边形面积，未修改标注")
    if closed_duplicate:
        result.append(result[0])
    return result, len(removed)


def selected_vertex_span(points, selected_indices):
    """Find one contiguous selected run, including a run across index zero."""
    ring = list(points)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    count = len(ring)
    selected = set(selected_indices)
    if any(index < 0 or index >= count for index in selected):
        raise ValueError("顶点已变化，请重新框选")
    if len(selected) < 3:
        raise ValueError("请选中至少三个连续顶点（包括要保留的首末顶点）")
    if len(selected) == count:
        raise ValueError("不能选中整个多边形，请只圈选要拉直的一段边界")
    starts = [index for index in selected if (index - 1) % count not in selected]
    if len(starts) != 1:
        raise ValueError("选区内包含多段不连续边界，请调整选区，只选一段")
    start = starts[0]
    return [(start + step) % count for step in range(len(selected))]


def _apply_straighten(widget, target, start: int, end: int, *, along_forward=False) -> int:
    from PyQt6 import QtCore

    ring = _points(target)
    points, removed = straighten_vertex_span(ring, start, end, along_forward=along_forward)
    target.points = [QtCore.QPointF(x, y) for x, y in points]
    widget.canvas.store_shapes()
    widget.canvas.shape_moved.emit()
    widget.canvas.update()
    widget.set_dirty()
    return removed


def vertices_in_selection(points, selection):
    """Select vertices inside or on a user-drawn polygon, including concavities."""
    area = _polygon(selection)
    if area is None:
        raise ValueError("请画至少三个选区角点，且选区边线不能交叉")
    ring = list(points)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    return [index for index, point in enumerate(ring) if area.covers(Point(point))]


class _BoxStraightenFilter:
    """User-drawn polygon selection with preview and explicit Enter commit."""

    @staticmethod
    def create(widget):
        from PyQt6 import QtCore, QtGui, QtWidgets

        class Overlay(QtWidgets.QWidget):
            def __init__(self, tool):
                super().__init__(widget.canvas)
                self.tool = tool
                self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
                self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
                self.hide()

            def paintEvent(self, event):
                tool = self.tool
                painter = QtGui.QPainter(self)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                cyan = QtGui.QColor(0, 190, 255)
                offset = widget.canvas.offset_to_center()
                scale = widget.canvas.scale
                if tool.region:
                    mapped = [(point + offset) * scale for point in tool.region]
                    painter.setPen(QtGui.QPen(cyan, 2, QtCore.Qt.PenStyle.DashLine))
                    painter.setBrush(QtGui.QColor(0, 190, 255, 25))
                    if tool.region_closed:
                        painter.drawPolygon(QtGui.QPolygonF(mapped))
                    else:
                        painter.drawPolyline(QtGui.QPolygonF(mapped))
                        if tool.hover is not None:
                            painter.drawLine(mapped[-1], (tool.hover + offset) * scale)
                    painter.setBrush(cyan)
                    for point in mapped:
                        painter.drawEllipse(point, 3, 3)
                    painter.drawEllipse(mapped[0], 6, 6)
                if tool.target is None:
                    return
                painter.setPen(QtGui.QPen(QtGui.QColor("white"), 1))
                painter.setBrush(cyan)
                for index in tool.selected:
                    point = (tool.target.points[index] + offset) * scale
                    painter.drawEllipse(point, 4, 4)
                if tool.span:
                    first = (tool.target.points[tool.span[0]] + offset) * scale
                    last = (tool.target.points[tool.span[-1]] + offset) * scale
                    painter.setPen(QtGui.QPen(QtGui.QColor(255, 120, 0), 3))
                    painter.drawLine(first, last)
                    painter.setBrush(QtGui.QColor(255, 120, 0))
                    painter.drawEllipse(first, 6, 6)
                    painter.drawEllipse(last, 6, 6)

        class Filter(QtCore.QObject):
            def __init__(self):
                super().__init__(widget.canvas)
                self.target = None
                self.region = []
                self.region_closed = False
                self.hover = None
                self.selected = []
                self.span = []
                self.swallow_release = False
                self.overlay = Overlay(self)

            def clear(self):
                self.target = None
                self.region = []
                self.region_closed = False
                self.hover = None
                self.selected = []
                self.span = []
                self.overlay.hide()

            def select_region(self):
                ring = _points(self.target)
                self.selected = []
                self.span = []
                try:
                    self.selected = vertices_in_selection(
                        ring, [(point.x(), point.y()) for point in self.region])
                    self.region_closed = True
                    self.span = selected_vertex_span(ring, self.selected)
                    # Validate before offering an executable preview.
                    straighten_vertex_span(ring, self.span[0], self.span[-1], along_forward=True)
                    message = (f"已圈选 {len(self.span)} 个顶点；橙色端点保留，"
                               f"按 Enter 删除中间 {len(self.span) - 2} 个并拉直；右键取消")
                except ValueError as error:
                    self.span = []
                    message = str(error)
                self.overlay.update()
                widget.statusBar().showMessage(message, 0)

            def add_corner(self, position, double_click=False):
                point = widget.canvas.transform_pos(position)
                if self.region_closed and double_click:
                    return
                if self.region_closed:
                    self.region = []
                    self.region_closed = False
                    self.selected = []
                    self.span = []
                scale = max(widget.canvas.scale, 0.01)
                if len(self.region) >= 3 and math.hypot(
                        point.x() - self.region[0].x(), point.y() - self.region[0].y()) * scale <= 10:
                    self.select_region()
                    return
                if not self.region or math.hypot(
                        point.x() - self.region[-1].x(), point.y() - self.region[-1].y()) * scale > 1:
                    self.region.append(point)
                self.hover = point
                if double_click:
                    self.select_region()
                else:
                    widget.statusBar().showMessage(
                        f"已画 {len(self.region)} 个选区角点；点回起点、双击或 Enter 闭合预览；Backspace 退回，右键取消", 0)
                self.overlay.update()

            def eventFilter(self, watched, event):
                if watched is not widget.canvas:
                    return False
                kind = event.type()
                if kind == QtCore.QEvent.Type.MouseButtonRelease and self.swallow_release:
                    self.swallow_release = False
                    return True
                action = widget.shared_boundary_box_straighten_action
                if not action.isChecked():
                    return False
                if not widget.canvas.editing() or getattr(widget.canvas, "is_brush_mode", False):
                    action.setChecked(False)
                    return False
                if kind == QtCore.QEvent.Type.Resize:
                    self.overlay.setGeometry(widget.canvas.rect())
                    return False
                if kind not in (QtCore.QEvent.Type.MouseButtonPress,
                                QtCore.QEvent.Type.MouseButtonDblClick,
                                QtCore.QEvent.Type.MouseButtonRelease,
                                QtCore.QEvent.Type.MouseMove, QtCore.QEvent.Type.KeyPress):
                    return False
                if self.target not in widget.canvas.shapes or self.target.locked:
                    action.setChecked(False)
                    widget.statusBar().showMessage("图形已变化或锁定，请重新选中多边形", 6000)
                    return True
                if kind == QtCore.QEvent.Type.KeyPress:
                    if event.key() == QtCore.Qt.Key.Key_Escape:
                        action.setChecked(False)
                        widget.statusBar().showMessage("已取消多边形圈选拉直", 5000)
                        return True
                    if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                        if not self.region_closed:
                            self.select_region()
                            return True
                        if not self.span:
                            widget.statusBar().showMessage("请重新画选区，圈住一段连续顶点，再按 Enter", 6000)
                            return True
                        try:
                            removed = _apply_straighten(widget, self.target, self.span[0],
                                                       self.span[-1], along_forward=True)
                        except ValueError as error:
                            widget.statusBar().showMessage(str(error), 6000)
                            return True
                        action.setChecked(False)
                        widget.statusBar().showMessage(
                            f"已圈选拉直，删除 {removed} 个中间顶点；Ctrl+Z 可撤销", 8000)
                        return True
                    # Prevent polygon editing shortcuts while previewing.
                    if event.key() == QtCore.Qt.Key.Key_Backspace:
                        if self.region:
                            self.region.pop()
                        self.region_closed = False
                        self.selected = []
                        self.span = []
                        self.overlay.update()
                        widget.statusBar().showMessage("已退回一个选区角点，请继续画选区并闭合", 0)
                        return True
                    if event.key() == QtCore.Qt.Key.Key_Delete:
                        return True
                    return False
                if kind in (QtCore.QEvent.Type.MouseButtonPress, QtCore.QEvent.Type.MouseButtonDblClick):
                    if event.button() == QtCore.Qt.MouseButton.RightButton:
                        self.swallow_release = True
                        action.setChecked(False)
                        widget.statusBar().showMessage("已取消多边形圈选拉直", 5000)
                        return True
                    if event.button() != QtCore.Qt.MouseButton.LeftButton:
                        return False
                    widget.canvas.setFocus()
                    self.overlay.setGeometry(widget.canvas.rect())
                    self.overlay.show()
                    self.overlay.raise_()
                    self.add_corner(event.position(), kind == QtCore.QEvent.Type.MouseButtonDblClick)
                    return True
                if kind == QtCore.QEvent.Type.MouseMove:
                    if self.region and not self.region_closed:
                        self.hover = widget.canvas.transform_pos(event.position())
                        self.overlay.update()
                        return True
                    return not bool(event.buttons())
                if kind == QtCore.QEvent.Type.MouseButtonRelease:
                    if event.button() == QtCore.Qt.MouseButton.LeftButton:
                        return True
                    return event.button() == QtCore.Qt.MouseButton.RightButton
                return False

        return Filter()


def _cancel_vertex_tools(widget, except_action=None):
    for name in ("shared_boundary_straighten_action", "shared_boundary_box_straighten_action"):
        action = getattr(widget, name, None)
        if action is not None and action is not except_action and action.isChecked():
            action.setChecked(False)


def _toggle_box_straighten(widget, enabled):
    tool = widget._shared_boundary_box_straighten_filter
    tool.clear()
    if not enabled:
        return
    action = widget.shared_boundary_box_straighten_action
    _cancel_vertex_tools(widget, except_action=action)
    selected = list(widget.canvas.selected_shapes)
    target = selected[0] if len(selected) == 1 else _resolve_list_target(widget)
    if (target is None or target.shape_type != "polygon" or target.locked
            or getattr(widget.canvas, "is_brush_mode", False)):
        action.setChecked(False)
        widget.statusBar().showMessage("请先结束画笔修改，并选中一个未锁定的多边形", 6000)
        return
    if not widget.canvas.editing():
        widget.set_edit_mode()
    widget.canvas.select_shapes([target])
    tool.target = target
    widget.canvas.setFocus()
    widget.statusBar().showMessage(
        "逐点画多边形选区（圈住首末顶点）；点回起点或双击闭合预览，再按 Enter 拉直；右键取消", 0)


class _StraightenClickFilter:
    """Factory wrapper so importing this module does not require Qt."""

    @staticmethod
    def create(widget):
        from PyQt6 import QtCore

        class Filter(QtCore.QObject):
            def __init__(self):
                super().__init__(widget.canvas)
                self.target = None
                self.start = None
                self.swallow_release = False

            def eventFilter(self, watched, event):
                if watched is not widget.canvas:
                    return False
                if event.type() == QtCore.QEvent.Type.MouseButtonRelease and self.swallow_release:
                    self.swallow_release = False
                    return True
                if not widget.shared_boundary_straighten_action.isChecked():
                    return False
                if event.type() == QtCore.QEvent.Type.MouseMove:
                    # Keep the chosen endpoint and the instruction visible;
                    # normal canvas hovering otherwise clears both.
                    return not bool(event.buttons())
                if event.type() == QtCore.QEvent.Type.MouseButtonRelease:
                    return event.button() in (
                        QtCore.Qt.MouseButton.LeftButton,
                        QtCore.Qt.MouseButton.RightButton,
                    )
                if event.type() != QtCore.QEvent.Type.MouseButtonPress:
                    return False
                if event.button() == QtCore.Qt.MouseButton.RightButton:
                    self.swallow_release = True
                    widget.shared_boundary_straighten_action.setChecked(False)
                    widget.statusBar().showMessage("已取消拉直边界", 5000)
                    return True
                if event.button() != QtCore.Qt.MouseButton.LeftButton:
                    return False
                self.swallow_release = True

                target = self.target
                if target not in widget.canvas.shapes:
                    widget.shared_boundary_straighten_action.setChecked(False)
                    widget.statusBar().showMessage("所选多边形已变化，请重新选择", 6000)
                    return True
                ring = _points(target)
                if len(ring) > 1 and ring[0] == ring[-1]:
                    ring.pop()
                position = widget.canvas.transform_pos(event.position())
                tolerance = 12.0 / max(widget.canvas.scale, 0.01)
                distances = [
                    math.hypot(x - position.x(), y - position.y())
                    for x, y in ring
                ]
                index = min(range(len(distances)), key=distances.__getitem__)
                if distances[index] > tolerance:
                    widget.statusBar().showMessage(
                        "请放大后点击边界上的顶点（绿色圆点）", 6000
                    )
                    return True
                if self.start is None:
                    self.start = index
                    target.highlight_vertex(index, target.MOVE_VERTEX)
                    widget.canvas.update()
                    widget.statusBar().showMessage(
                        "已选起点；请点击弯折段另一端的顶点，右键可取消", 8000
                    )
                    return True
                try:
                    removed = _apply_straighten(widget, target, self.start, index)
                except ValueError as error:
                    widget.statusBar().showMessage(str(error), 8000)
                    return True
                widget.shared_boundary_straighten_action.setChecked(False)
                widget.statusBar().showMessage(
                    f"已删除 {removed} 个中间顶点并拉直；Ctrl+Z 可撤销", 8000
                )
                return True

        return Filter()


def _toggle_straighten(widget, enabled: bool) -> None:
    tool = widget._shared_boundary_straighten_filter
    if tool.target is not None:
        tool.target.highlight_clear()
        widget.canvas.update()
    tool.start = None
    tool.target = None
    if not enabled:
        return
    _cancel_vertex_tools(widget, except_action=widget.shared_boundary_straighten_action)
    if getattr(widget.canvas, "is_brush_mode", False):
        widget.statusBar().showMessage("请先右键结束画笔修改，再拉直边界", 6000)
        widget.shared_boundary_straighten_action.setChecked(False)
        return
    selected = list(widget.canvas.selected_shapes)
    if len(selected) != 1:
        target = _resolve_list_target(widget)
        selected = [target] if target is not None else []
    if len(selected) != 1 or selected[0].shape_type != "polygon":
        widget.statusBar().showMessage("请先在编辑模式中选中一个多边形", 6000)
        widget.shared_boundary_straighten_action.setChecked(False)
        return
    if selected[0].locked:
        widget.statusBar().showMessage("图形已锁定，请先解锁", 6000)
        widget.shared_boundary_straighten_action.setChecked(False)
        return
    if not widget.canvas.editing():
        widget.set_edit_mode()
    widget.canvas.select_shapes([selected[0]])
    tool.target = selected[0]
    widget.statusBar().showMessage(
        "请依次点击弯折段两端的顶点；将删除较短边界段内的中间顶点，右键取消", 10000
    )


def _replace_undo_snapshot(widget) -> None:
    if widget.canvas.shapes_backups:
        widget.canvas.shapes_backups[-1] = [
            shape.copy() for shape in widget.canvas.shapes
        ]
    else:
        widget.canvas.store_shapes()


def _clip_new_regions(widget, new_shapes) -> bool:
    """Subtract the fixed existing regions from new annotations only."""
    from PyQt6 import QtCore

    candidates = list(new_shapes)
    undo_history = list(widget.canvas.shapes_backups)
    candidate_ids = {id(shape) for shape in candidates}
    references = [
        shape for shape in widget.canvas.shapes
        if id(shape) not in candidate_ids
        and shape.shape_type == "polygon"
        and shape.label not in SPECIAL_LABELS
    ]
    changed = False
    removed = 0
    skipped = 0
    for target in candidates:
        if (
            target not in widget.canvas.shapes
            or target.shape_type != "polygon"
            or target.label in SPECIAL_LABELS
        ):
            continue
        if target.locked:
            skipped += 1
            continue
        try:
            geometry = _annotation_geometry(_points(target))
            if geometry is None:
                continue
            cutters = [
                _annotation_geometry(_points(reference))
                for reference in references if reference.label != target.label
            ]
            cutters = [cutter for cutter in cutters if cutter is not None]
            if not cutters:
                continue
            occupied = unary_union(cutters)
            if geometry.intersection(occupied).area <= AREA_EPSILON:
                continue
            parts = _rings_from_geometry(geometry.difference(occupied))
        except Exception:
            LOG.exception("Existing-region clipping failed for %s", target.label)
            skipped += 1
            continue

        index = widget.canvas.shapes.index(target)
        if not parts:
            widget.remove_labels([target])
            # Refreshing the real Shapes list may already remove it from canvas.
            if target in widget.canvas.shapes:
                widget.canvas.shapes.remove(target)
            widget.canvas.selected_shapes = [
                shape for shape in widget.canvas.selected_shapes if shape is not target
            ]
            if getattr(widget, "_shared_boundary_list_shape", None) is target:
                widget._shared_boundary_list_shape = None
            removed += 1
        else:
            original = target.copy()
            target.points = [QtCore.QPointF(x, y) for x, y in parts[0]]
            for offset, ring in enumerate(parts[1:], start=1):
                piece = original.copy()
                piece.points = [QtCore.QPointF(x, y) for x, y in ring]
                piece.selected = False
                widget.canvas.shapes.insert(index + offset, piece)
                widget.add_label(piece)
        changed = True

    if changed:
        # Keep completion and automatic clipping in one undo operation.
        widget.canvas.update()
        widget._refresh_shape_filters()
        # Adding/removing real list rows can trigger canvas.load_shapes(),
        # which adds intermediate snapshots. Discard only those extra entries.
        widget.canvas.shapes_backups[:] = undo_history
        _replace_undo_snapshot(widget)
        widget.set_dirty()
        message = "已按旧区域边界裁剪新多边形；旧区域保持不变，Ctrl+Z 可撤销"
        if removed:
            message += f"；{removed} 个新多边形完全被覆盖，已移除"
        widget.statusBar().showMessage(message, 8000)
    if skipped:
        widget.statusBar().showMessage(
            f"有 {skipped} 个新多边形因锁定或处理失败未裁剪，请检查标注", 8000
        )
    return changed


def _carve_widget(
    widget, new_shapes, *, force: bool = False, preserve_existing: bool = True
) -> bool:
    """Default to existing-region priority; retain the explicit reverse tool."""
    from PyQt6 import QtCore

    if not force and not widget.shared_boundary_action.isChecked():
        return False
    if preserve_existing:
        return _clip_new_regions(widget, new_shapes)
    changed = False
    skipped_locked = 0
    for new_shape in list(new_shapes):
        if (
            new_shape not in widget.canvas.shapes
            or new_shape.shape_type != "polygon"
            or new_shape.label in SPECIAL_LABELS
        ):
            continue
        fresh_points = _points(new_shape)
        for old_shape in list(widget.canvas.shapes):
            if (
                old_shape is new_shape
                or old_shape.shape_type != "polygon"
                or old_shape.label == new_shape.label
                or old_shape.label in SPECIAL_LABELS
            ):
                continue
            try:
                parts = subtract_coordinates(_points(old_shape), fresh_points)
            except Exception:
                LOG.exception("Shared-edge clipping failed for %s", old_shape.label)
                continue
            if parts is None:
                continue
            if old_shape.locked:
                skipped_locked += 1
                continue

            index = widget.canvas.shapes.index(old_shape)
            if not parts:
                widget.remove_labels([old_shape])
                if old_shape in widget.canvas.shapes:
                    widget.canvas.shapes.remove(old_shape)
                widget.canvas.selected_shapes = [
                    shape for shape in widget.canvas.selected_shapes
                    if shape is not old_shape
                ]
            else:
                original = old_shape.copy()
                old_shape.points = [QtCore.QPointF(x, y) for x, y in parts[0]]
                for offset, ring in enumerate(parts[1:], start=1):
                    piece = original.copy()
                    piece.points = [QtCore.QPointF(x, y) for x, y in ring]
                    piece.selected = False
                    widget.canvas.shapes.insert(index + offset, piece)
                    widget.add_label(piece)
            changed = True

    if changed:
        # The app records the completed new shape just before calling us.
        # Replace that snapshot so one Undo restores both the new and old
        # polygons together instead of reintroducing an overlapping state.
        _replace_undo_snapshot(widget)
        widget.canvas.update()
        widget._refresh_shape_filters()
        widget.set_dirty()
    if skipped_locked:
        widget.statusBar().showMessage(
            f"共边处理跳过了 {skipped_locked} 个已锁定图形", 6000
        )
    return changed


def _remember_list_shape(widget, index) -> None:
    """Remember the clicked Shapes row even if canvas hover changes later."""
    item = widget.label_list.model().itemFromIndex(index)
    shape = item.shape() if item is not None else None
    box_tool = getattr(widget, "_shared_boundary_box_straighten_filter", None)
    if box_tool is not None and box_tool.target is not None and box_tool.target is not shape:
        _cancel_vertex_tools(widget)
    widget._shared_boundary_list_shape = shape
    if shape is not None:
        widget.shared_boundary_deduct_button.setText(
            f"从“{shape.label}”中扣除其他类别的重叠"
        )


def _resolve_list_target(widget):
    """Find the live canvas shape when a remembered list object has gone stale."""
    stored = widget._shared_boundary_list_shape
    if stored is None or stored.shape_type != "polygon":
        return None
    shapes = widget.canvas.shapes
    if stored in shapes:
        return stored

    label_list = getattr(widget, "label_list", None)
    if label_list is not None:
        selected = [
            item.shape() for item in label_list.selected_items()
            if item.shape() in shapes
            and item.shape().shape_type == "polygon"
            and item.shape().label == stored.label
        ]
        if len(selected) == 1:
            return selected[0]

    canvas_selected = [
        shape for shape in widget.canvas.selected_shapes
        if shape in shapes
        and shape.shape_type == "polygon"
        and shape.label == stored.label
    ]
    if len(canvas_selected) == 1:
        return canvas_selected[0]

    candidates = [
        shape for shape in shapes
        if shape.shape_type == "polygon" and shape.label == stored.label
    ]
    return candidates[0] if len(candidates) == 1 else None


def _deduct_from_list(widget, *, same_class=False) -> bool:
    """Clip the clicked polygon, optionally retaining other same-class objects."""
    from PyQt6 import QtCore, QtWidgets

    target = _resolve_list_target(widget)
    if target is None:
        stored = widget._shared_boundary_list_shape
        if stored is not None and stored.shape_type != "polygon":
            message = f"“{stored.label}”当前是 {stored.shape_type}，此按钮只能处理多边形"
        elif stored is not None:
            message = f"“{stored.label}”列表记录与画布不同步；请在编辑模式中重新点选该行"
        else:
            message = "请先单击 Shapes 列表中需要扣除重叠的多边形名称"
        widget.statusBar().showMessage(
            message, 7000
        )
        return False
    widget._shared_boundary_list_shape = target
    if target.locked:
        widget.statusBar().showMessage("所点击的图形已锁定，请先解锁", 7000)
        return False
    target_geometry = _annotation_geometry(_points(target))
    if target_geometry is None:
        widget.statusBar().showMessage("所点击的多边形无效，无法扣除", 7000)
        return False

    references = []
    invalid_labels = set()
    other_shapes = []
    for shape in widget.canvas.shapes:
        if shape is target or shape.label in SPECIAL_LABELS:
            continue
        if same_class:
            if shape.label != target.label:
                continue
            # Pieces explicitly assigned to one object are not separate peers.
            if target.group_id is not None and shape.group_id == target.group_id:
                continue
        elif shape.label == target.label:
            continue
        other_shapes.append(shape)
        if shape.shape_type != "polygon":
            continue
        geometry = _annotation_geometry(_points(shape))
        if geometry is None:
            invalid_labels.add(shape.label)
            continue
        if geometry is not None and target_geometry.intersection(geometry).area > AREA_EPSILON:
            references.append((shape, geometry))
    labels = sorted({shape.label for shape, _ in references})
    if not labels:
        if same_class:
            message = "未发现与当前对象重叠的其他同类多边形（相同非空 Group ID 视为同一对象）"
        elif not other_shapes:
            message = "没有找到其他类别的已完成图形；请确认两者都已保存且类别不同"
        elif invalid_labels:
            message = "其他类别的多边形轮廓无法修复，请检查：" + "、".join(sorted(invalid_labels))
        elif other_shapes and all(shape.shape_type != "polygon" for shape in other_shapes):
            message = "其他类别不是多边形，请先将其转换为多边形"
        else:
            message = "未发现与所点击图形重叠的其他类别多边形"
        widget.statusBar().showMessage(
            message, 7000
        )
        return False
    if len(labels) == 1:
        reference_label = labels[0]
    else:
        reference_label, accepted = QtWidgets.QInputDialog.getItem(
            widget, "选择保留边界", f"从“{target.label}”中扣除哪一类？", labels, 0, False
        )
        if not accepted:
            return False

    reference_geometry = unary_union(
        [geometry for shape, geometry in references if shape.label == reference_label]
    )
    try:
        parts = _rings_from_geometry(target_geometry.difference(reference_geometry))
    except Exception:
        LOG.exception("Shapes-row clipping failed for %s", target.label)
        widget.statusBar().showMessage("扣除失败，标注未修改", 7000)
        return False

    refinement = getattr(widget, "shared_boundary_refine_action", None)
    if refinement is not None and refinement.isChecked():
        refinement.setChecked(False)
    _cancel_vertex_tools(widget)
    index = widget.canvas.shapes.index(target)
    if not parts:
        widget.remove_labels([target])
        widget.canvas.shapes.pop(index)
        widget.canvas.selected_shapes = [
            shape for shape in widget.canvas.selected_shapes if shape is not target
        ]
        widget._shared_boundary_list_shape = None
        widget.shared_boundary_deduct_button.setText(
            "点下方类别名称，从它自身扣除重叠"
        )
    else:
        original = target.copy()
        target.points = [QtCore.QPointF(x, y) for x, y in parts[0]]
        for offset, ring in enumerate(parts[1:], start=1):
            piece = original.copy()
            piece.points = [QtCore.QPointF(x, y) for x, y in ring]
            piece.selected = False
            widget.canvas.shapes.insert(index + offset, piece)
            widget.add_label(piece)

    widget.canvas.store_shapes()
    widget.canvas.update()
    widget._refresh_shape_filters()
    widget.set_dirty()
    message = (
        f"已从当前“{target.label}”对象中扣除 {len(references)} 个同类对象的重叠；其他对象未修改，Ctrl+Z 可撤销"
        if same_class else
        f"已从“{target.label}”中扣除“{reference_label}”，按其边界共边；“{reference_label}”未修改"
    )
    widget.statusBar().showMessage(message, 7000)
    return True


def transfer_shared_boundary(domain, edited_points):
    """Return the updated domain and complementary neighbor rings.

    The domain is the union captured when refinement begins. Growth of the
    edited polygon expands it; shrinkage is assigned to its neighbor.
    """
    edited = _annotation_geometry(edited_points)
    if edited is None:
        raise ValueError("edited polygon is empty or invalid")
    expanded_domain = domain.union(edited)
    return expanded_domain, _rings_from_geometry(expanded_domain.difference(edited))


def _stop_refinement(widget) -> None:
    widget._shared_boundary_session = None


def _enable_sam2_detail_preset(widget) -> bool:
    """Use local crops and retain more contour vertices for the loaded SAM2."""
    panel = widget.auto_labeling_widget
    config = panel.model_manager.loaded_model_config
    model = config.get("model") if isinstance(config, dict) else None
    if model is None or model.__class__.__name__ != "SegmentAnything2":
        widget.statusBar().showMessage(
            "请先在自动标注面板加载 Segment Anything 2.1 模型", 7000
        )
        return False
    panel.mask_fineness_slider.setValue(3)  # epsilon=0.0003 vs default 0.001
    if not panel.button_cropping.isChecked():
        panel.button_cropping.click()
    widget.statusBar().showMessage(
        "已开启 SAM2 细节优先：请先框住局部堆体，再加前景点和背景点；轮廓精细度设为 0.0003",
        10000,
    )
    return True


def _start_refinement(widget) -> None:
    """Bind one selected polygon to an adjacent class for live edge transfer."""
    from PyQt6 import QtWidgets

    selected = list(widget.canvas.selected_shapes)
    if len(selected) != 1 or selected[0].shape_type != "polygon":
        widget.statusBar().showMessage("请先在编辑模式中选中一个多边形", 6000)
        widget.shared_boundary_refine_action.setChecked(False)
        return
    target = selected[0]
    if target.locked:
        widget.statusBar().showMessage("选中图形已锁定，请先解锁", 6000)
        widget.shared_boundary_refine_action.setChecked(False)
        return
    target_geometry = _annotation_geometry(_points(target))
    if target_geometry is None:
        widget.statusBar().showMessage("选中多边形无效，无法共边精修", 6000)
        widget.shared_boundary_refine_action.setChecked(False)
        return

    adjacent = []
    for shape in widget.canvas.shapes:
        if (
            shape is target
            or shape.shape_type != "polygon"
            or shape.label == target.label
            or shape.locked
        ):
            continue
        geometry = _annotation_geometry(_points(shape))
        if geometry is not None and geometry.distance(target_geometry) <= 1e-6:
            adjacent.append((shape, geometry))
    labels = sorted({shape.label for shape, _ in adjacent})
    if not labels:
        widget.statusBar().showMessage(
            "没有找到接触的其他类别；请先让新区域与旧区域重叠并完成扣除", 7000
        )
        widget.shared_boundary_refine_action.setChecked(False)
        return
    if len(labels) == 1:
        neighbor_label = labels[0]
    else:
        neighbor_label, accepted = QtWidgets.QInputDialog.getItem(
            widget, "共边精修", "选择要联动的相邻类别：", labels, 0, False
        )
        if not accepted:
            widget.shared_boundary_refine_action.setChecked(False)
            return

    neighbors = [
        shape for shape, _ in adjacent if shape.label == neighbor_label
    ]
    geometries = [target_geometry] + [
        geometry for shape, geometry in adjacent if shape.label == neighbor_label
    ]
    widget._shared_boundary_session = {
        "image_path": widget.image_path,
        "target": target,
        "target_label": target.label,
        "last_target": target_geometry,
        "neighbor_label": neighbor_label,
        "neighbor_parts": neighbors,
        "last_neighbor": unary_union(geometries[1:]),
        "neighbor_template": neighbors[0].copy(),
        "insert_at": min(widget.canvas.shapes.index(shape) for shape in neighbors),
        "domain": unary_union(geometries),
    }
    widget.statusBar().showMessage(
        f"共边精修已开启：修改“{target.label}”，相邻的“{neighbor_label}”会同步伸缩",
        8000,
    )


def _update_refinement(widget) -> bool:
    """Transfer the area gained or lost by the selected polygon on edit."""
    from PyQt6 import QtCore

    session = widget._shared_boundary_session
    if not session or not widget.shared_boundary_refine_action.isChecked():
        return False
    target = session["target"]
    if (
        widget.image_path != session["image_path"]
        or target not in widget.canvas.shapes
        or target.label != session["target_label"]
    ):
        widget.shared_boundary_refine_action.setChecked(False)
        return False
    edited = _annotation_geometry(_points(target))
    if edited is None:
        widget.statusBar().showMessage("修改后的多边形无效，邻区未更新", 6000)
        return False
    if edited.equals(session["last_target"]):
        current_neighbors = [
            _annotation_geometry(_points(shape))
            for shape in session["neighbor_parts"]
            if shape in widget.canvas.shapes
        ]
        current_neighbors = [shape for shape in current_neighbors if shape is not None]
        current_neighbor = unary_union(current_neighbors) if current_neighbors else Polygon()
        if not current_neighbor.equals(session["last_neighbor"]):
            widget.shared_boundary_refine_action.setChecked(False)
            widget.statusBar().showMessage(
                "相邻图形已单独修改；共边精修已结束，请重新开启", 7000
            )
        return False

    try:
        domain, rings = transfer_shared_boundary(session["domain"], _points(target))
    except Exception:
        LOG.exception("Shared-edge refinement failed")
        widget.statusBar().showMessage("共边精修失败，邻区未更新", 6000)
        return False

    old_parts = list(session["neighbor_parts"])
    if old_parts:
        widget.remove_labels(old_parts)
        widget.canvas.shapes[:] = [
            shape for shape in widget.canvas.shapes if shape not in old_parts
        ]
        widget.canvas.selected_shapes = [
            shape for shape in widget.canvas.selected_shapes if shape not in old_parts
        ]
    new_parts = []
    for offset, ring in enumerate(rings):
        shape = session["neighbor_template"].copy()
        shape.points = [QtCore.QPointF(x, y) for x, y in ring]
        shape.selected = False
        index = min(session["insert_at"] + offset, len(widget.canvas.shapes))
        widget.canvas.shapes.insert(index, shape)
        widget.add_label(shape)
        new_parts.append(shape)

    session["neighbor_parts"] = new_parts
    session["last_neighbor"] = unary_union(
        [Polygon(ring) for ring in rings]
    ) if rings else Polygon()
    session["domain"] = domain
    session["last_target"] = edited
    _replace_undo_snapshot(widget)
    widget.canvas.update()
    widget._refresh_shape_filters()
    widget.set_dirty()
    return True


def _resume_polygon_draft(widget, shape, points, undo_history, *, brush: bool) -> None:
    """Resume an unlabelled polygon after closing its completion dialog."""
    from PyQt6 import QtCore

    canvas = widget.canvas
    if shape in canvas.shapes:
        canvas.shapes.remove(shape)
    shape.points = [QtCore.QPointF(point) for point in points]
    shape.label = None
    shape.selected = False
    shape.set_open()
    shape.highlight_clear()
    canvas.current = shape
    canvas.create_mode = "polygon"
    canvas.set_editing(False)
    canvas._brush_drawing = brush
    canvas.line.points = [QtCore.QPointF(points[-1]), QtCore.QPointF(points[-1])]
    # Completion records a snapshot before the dialog opens; it is not a
    # committed annotation when the user rejects that dialog.
    canvas.shapes_backups[:] = undo_history[:-1]
    canvas.set_hiding(True)
    widget.toggle_drawing_sensitive(True)
    canvas.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
    canvas.update()
    method = "移动鼠标继续描边" if brush else "单击继续添加顶点"
    widget.statusBar().showMessage(
        f"已取消类别填写，保留 {len(points)} 个顶点；{method}，Enter 完成；Esc 放弃草稿", 10000
    )


def _following_polygon(canvas) -> bool:
    return (
        canvas.drawing()
        and canvas.create_mode == "polygon"
        and canvas.current is not None
        and canvas._brush_drawing
    )


def _install_brush_navigation(widget_class) -> None:
    """Anchor zoom and pan without recording navigation as polygon vertices."""
    from PyQt6 import QtCore
    from anylabeling.views.labeling.widgets.canvas import Canvas

    original_hint = Canvas.minimumSizeHint
    original_move = Canvas.mouseMoveEvent
    original_press = Canvas.mousePressEvent
    original_release = Canvas.mouseReleaseEvent
    original_double_click = Canvas.mouseDoubleClickEvent
    original_focus_out = Canvas.focusOutEvent
    original_reset = Canvas.reset_state
    original_wheel = Canvas.wheelEvent
    original_zoom = widget_class.zoom_request
    original_paint = widget_class.paint_canvas
    original_fit_window = widget_class.set_fit_window
    original_fit_width = widget_class.set_fit_width

    def minimum_hint(self):
        hint = original_hint(self)
        padding = getattr(self, "_shared_boundary_zoom_padding", None)
        if padding and self.pixmap is not None and not self.pixmap.isNull():
            hint += QtCore.QSize(2 * padding[0], 2 * padding[1])
        return hint

    def mouse_move(self, event):
        position = QtCore.QPointF(event.globalPosition())
        self._shared_boundary_pointer_global = position
        drag = getattr(self, "_shared_boundary_middle_pan", None)
        if drag is not None:
            if event.buttons() & QtCore.Qt.MouseButton.MiddleButton:
                owner = self._shared_boundary_owner
                delta = position - drag[0]
                for orientation, shift in (
                    (QtCore.Qt.Orientation.Horizontal, delta.x()),
                    (QtCore.Qt.Orientation.Vertical, delta.y()),
                ):
                    owner.set_scroll(orientation, drag[1][orientation] - shift)
                self.override_cursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            # Recover when the button was released outside the canvas.
            stop_pan(self)
        if paused(self):
            event.accept()
            return
        if not _following_polygon(self):
            return original_move(self, event)
        navigating = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier)
        navigating = navigating or self._space_pressed or self._space_panning
        anchor = getattr(self, "_shared_boundary_navigation_global", None)
        if navigating:
            self._shared_boundary_navigation_global = position
        stationary = anchor is not None and (
            abs(position.x() - anchor.x()) <= 1
            and abs(position.y() - anchor.y()) <= 1
        )
        if navigating or stationary:
            # Still update the preview/crosshair, without adding or closing points.
            draft = self.current
            self._brush_drawing = False
            try:
                return original_move(self, event)
            finally:
                if self.current is draft and self.drawing():
                    self._brush_drawing = True
        self._shared_boundary_navigation_global = None
        return original_move(self, event)

    def paused(canvas):
        draft = getattr(canvas, "_shared_boundary_paused_draft", None)
        return draft is not None and canvas.current is draft and _following_polygon(canvas)

    def stop_pan(canvas):
        canvas._shared_boundary_middle_pan = None
        canvas._shared_boundary_zoom_anchor = None
        canvas.restore_cursor()
        if paused(canvas):
            canvas._shared_boundary_owner.statusBar().showMessage(
                "描边已暂停；移回最后一个边界点附近，单击左键继续描边（中键仍可平移）", 10000
            )

    def mouse_press(self, event):
        owner = getattr(self, "_shared_boundary_owner", None)
        if (event.button() == QtCore.Qt.MouseButton.MiddleButton
                and owner is not None and not self.is_loading
                and self.drawing() and self.create_mode == "polygon"
                and self.pixmap is not None and not self.pixmap.isNull()):
            if _following_polygon(self):
                self._shared_boundary_paused_draft = self.current
                # Freeze the preview at the last recorded vertex as well.
                self.line.points = [self.current[-1], self.current[-1]]
            viewport = owner._canvas_scroll_area.viewport()
            position = QtCore.QPointF(event.position())
            image_point = self.transform_pos(position)
            viewport_point = QtCore.QPointF(self.mapTo(viewport, QtCore.QPoint())) + position
            # Permit panning fitted / small images, preserving their position
            # when the scrollable margin is first introduced.
            self._shared_boundary_zoom_padding = (viewport.width(), viewport.height())
            self.updateGeometry()
            self.adjustSize()
            projected = (image_point + self.offset_to_center()) * self.scale
            origin = self.mapTo(viewport, QtCore.QPoint())
            for orientation, shift in (
                (QtCore.Qt.Orientation.Horizontal, origin.x() + projected.x() - viewport_point.x()),
                (QtCore.Qt.Orientation.Vertical, origin.y() + projected.y() - viewport_point.y()),
            ):
                owner.set_scroll(orientation, owner.scroll_bars[orientation].value() + shift)
            self._shared_boundary_middle_pan = (
                QtCore.QPointF(event.globalPosition()),
                {orientation: bar.value() for orientation, bar in owner.scroll_bars.items()},
            )
            self._shared_boundary_zoom_anchor = None
            self.override_cursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            self.update()
            event.accept()
            return
        if getattr(self, "_shared_boundary_middle_pan", None) is not None:
            event.accept()
            return
        if paused(self) and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._shared_boundary_paused_draft = None
            self._shared_boundary_navigation_global = QtCore.QPointF(event.globalPosition())
            owner.statusBar().showMessage("已恢复连续描边；移动鼠标继续，Enter 完成", 5000)
            # This click resumes following; it is not a new polygon vertex.
            event.accept()
            return
        return original_press(self, event)

    def mouse_release(self, event):
        if (event.button() == QtCore.Qt.MouseButton.MiddleButton
                and getattr(self, "_shared_boundary_middle_pan", None) is not None):
            stop_pan(self)
            event.accept()
            return
        return original_release(self, event)

    def double_click(self, event):
        if paused(self) or getattr(self, "_shared_boundary_middle_pan", None) is not None:
            event.accept()
            return
        return original_double_click(self, event)

    def focus_out(self, event):
        if getattr(self, "_shared_boundary_middle_pan", None) is not None:
            stop_pan(self)
        return original_focus_out(self, event)

    def reset(self, *args, **kwargs):
        self._shared_boundary_middle_pan = None
        self._shared_boundary_paused_draft = None
        return original_reset(self, *args, **kwargs)

    def wheel(self, event):
        if _following_polygon(self):
            position = QtCore.QPointF(event.globalPosition())
            self._shared_boundary_pointer_global = position
            self._shared_boundary_navigation_global = position
            owner = getattr(self, "_shared_boundary_owner", None)
            if owner is not None and event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                # Keep the wheel's floating-point position (the stock signal
                # rounds to QPoint and loses subpixel accuracy at low zoom).
                owner.zoom_request(event.angleDelta().y(), event.position())
                event.accept()
                return
        return original_wheel(self, event)

    def paint(self):
        canvas = self.canvas
        if _following_polygon(canvas) and canvas.scale != 0.01 * self.zoom_widget.value():
            position = getattr(canvas, "_shared_boundary_pointer_global", None)
            if position is not None:
                canvas._shared_boundary_navigation_global = QtCore.QPointF(position)
        return original_paint(self)

    def zoom(self, delta, position):
        canvas = self.canvas
        if not _following_polygon(canvas):
            return original_zoom(self, delta, position)
        if not delta:
            return
        viewport = self._canvas_scroll_area.viewport()
        position = QtCore.QPointF(position)
        image_point = canvas.transform_pos(position)
        viewport_point = QtCore.QPointF(canvas.mapTo(viewport, QtCore.QPoint())) + position
        global_point = QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint())) + position
        cached_anchor = getattr(canvas, "_shared_boundary_zoom_anchor", None)
        if cached_anchor is not None and cached_anchor[0] == global_point:
            image_point = cached_anchor[1]
        canvas._shared_boundary_zoom_anchor = (global_point, image_point)
        canvas._shared_boundary_pointer_global = global_point
        canvas._shared_boundary_navigation_global = global_point
        # A scrollable margin makes anchoring possible even when the image is
        # smaller than the viewport; otherwise scrollbar limits force a jump.
        canvas._shared_boundary_zoom_padding = (viewport.width(), viewport.height())
        canvas.updateGeometry()
        self.add_zoom(1.1 if delta > 0 else 0.9)
        canvas.adjustSize()
        projected = (image_point + canvas.offset_to_center()) * canvas.scale
        origin = canvas.mapTo(viewport, QtCore.QPoint())
        for orientation, shift in (
            (QtCore.Qt.Orientation.Horizontal, origin.x() + projected.x() - viewport_point.x()),
            (QtCore.Qt.Orientation.Vertical, origin.y() + projected.y() - viewport_point.y()),
        ):
            self.set_scroll(orientation, self.scroll_bars[orientation].value() + shift)
        canvas.update()

    def clear_padding(self):
        canvas = self.canvas
        position = getattr(canvas, "_shared_boundary_pointer_global", None)
        canvas._shared_boundary_navigation_global = position
        canvas._shared_boundary_zoom_padding = None
        canvas._shared_boundary_zoom_anchor = None
        canvas.updateGeometry()

    def fit_window(self, *args, **kwargs):
        clear_padding(self)
        return original_fit_window(self, *args, **kwargs)

    def fit_width(self, *args, **kwargs):
        clear_padding(self)
        return original_fit_width(self, *args, **kwargs)

    Canvas.minimumSizeHint = minimum_hint
    Canvas.mouseMoveEvent = mouse_move
    Canvas.mousePressEvent = mouse_press
    Canvas.mouseReleaseEvent = mouse_release
    Canvas.mouseDoubleClickEvent = double_click
    Canvas.focusOutEvent = focus_out
    Canvas.reset_state = reset
    Canvas.wheelEvent = wheel
    widget_class.zoom_request = zoom
    widget_class.paint_canvas = paint
    widget_class.set_fit_window = fit_window
    widget_class.set_fit_width = fit_width


def install() -> None:
    """Add shared-edge mode to the installed UI without replacing its files."""
    from PyQt6 import QtGui, QtWidgets
    from anylabeling.views.labeling.label_widget import LabelingWidget

    if getattr(LabelingWidget, "_shared_boundary_installed", False):
        return

    _install_brush_navigation(LabelingWidget)
    original_init = LabelingWidget.__init__
    original_new_shape = LabelingWidget.new_shape
    original_finish_auto = LabelingWidget.finish_auto_labeling_object
    original_undo = LabelingWidget.undo_shape_edit
    original_load_file = LabelingWidget.load_file

    def init_with_shared_boundary(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.canvas._shared_boundary_owner = self
        # The stock list uses checkboxes for visibility and canvas hover can
        # look like a lasting selection. Provide an explicit row-based action.
        deduct_button = QtWidgets.QPushButton(
            "点下方类别名称，从它自身扣除重叠", self.shape_dock.parentWidget()
        )
        deduct_button.setToolTip(
            "修改所点击行的多边形；按重叠的其他类别边界扣除，其他类别保持不变；左侧勾选框只控制显示"
        )
        self.shared_boundary_deduct_button = deduct_button
        self._shared_boundary_list_shape = None
        self.shape_dock.parentWidget().layout().insertWidget(1, deduct_button)
        self.label_list.clicked.connect(
            lambda index: _remember_list_shape(self, index)
        )
        deduct_button.clicked.connect(lambda: _deduct_from_list(self))
        same_deduct = QtWidgets.QPushButton("从当前对象扣除同类重叠", self)
        same_deduct.setToolTip(
            "先点选需要缩小的 Shapes 行；从该对象扣除其他同类对象的重叠，保留其他对象边界。相同非空 Group ID 不互相扣除"
        )
        same_deduct.clicked.connect(lambda: _deduct_from_list(self, same_class=True))
        self.shared_boundary_same_deduct_button = same_deduct
        self.shape_dock.parentWidget().layout().insertWidget(2, same_deduct)

        action = QtGui.QAction("旧区域优先：自动裁剪新多边形（共边）", self)
        action.setCheckable(True)
        action.setChecked(True)
        action.setToolTip("保留已有类别的边界；新多边形完成后，自动从新区域扣除其他类别旧区域的重叠，锁定旧区域也作为参考")
        self.shared_boundary_action = action
        self.menus.edit.addSeparator()
        self.menus.edit.addAction(action)

        point_spacing = QtGui.QAction("画笔多边形点间距…", self)
        point_spacing.setToolTip(
            "调整鼠标移动自动加点的最小距离（屏幕像素，1–200）；建议先试 5–10，修改后点击 Save 保存"
        )
        point_spacing.triggered.connect(
            lambda: self.open_settings_dialog(field_key="canvas.brush.point_distance")
        )
        self.shared_boundary_point_spacing_action = point_spacing
        self.menus.edit.addAction(point_spacing)

        reconcile = QtGui.QAction("以画布选中图形为准裁剪其他类别", self)
        reconcile.setToolTip("选中多边形向外扩展后，再次从其他类别中扣除重叠部分")
        reconcile.triggered.connect(
            lambda: _carve_widget(
                self, list(self.canvas.selected_shapes), force=True,
                preserve_existing=False,
            )
        )
        self.menus.edit.addAction(reconcile)

        refine = QtGui.QAction("共边精修：联动相邻类别", self)
        refine.setCheckable(True)
        refine.setToolTip("选中一个多边形后开启；修边时相邻类别同步补齐或退让")
        self.shared_boundary_refine_action = refine
        self._shared_boundary_session = None
        refine.toggled.connect(
            lambda enabled: _start_refinement(self)
            if enabled
            else _stop_refinement(self)
        )
        self.menus.edit.addAction(refine)
        self.canvas.shape_moved.connect(lambda: _update_refinement(self))

        straighten = QtGui.QAction("拉直一段边界（点起点和终点）", self)
        straighten.setCheckable(True)
        straighten.setToolTip(
            "选中多边形后，依次点弯折段两端的顶点；删除较短边界段内的中间顶点"
        )
        self.shared_boundary_straighten_action = straighten
        self._shared_boundary_straighten_filter = _StraightenClickFilter.create(self)
        self.canvas.installEventFilter(self._shared_boundary_straighten_filter)
        straighten.toggled.connect(lambda enabled: _toggle_straighten(self, enabled))
        self.menus.edit.addAction(straighten)

        box_straighten = QtGui.QAction("多边形圈选顶点拉直", self)
        box_straighten.setCheckable(True)
        box_straighten.setToolTip("逐点画多边形选区，点回起点或双击闭合；预览后按 Enter，保留首末顶点并拉直")
        self.shared_boundary_box_straighten_action = box_straighten
        self._shared_boundary_box_straighten_filter = _BoxStraightenFilter.create(self)
        self.canvas.installEventFilter(self._shared_boundary_box_straighten_filter)
        box_straighten.toggled.connect(lambda enabled: _toggle_box_straighten(self, enabled))
        self.menus.edit.addAction(box_straighten)
        box_button = QtWidgets.QPushButton("多边形圈选顶点拉直", self)
        box_button.setCheckable(True)
        box_button.setToolTip(box_straighten.toolTip())
        box_button.clicked.connect(box_straighten.setChecked)
        box_straighten.toggled.connect(
            lambda _checked: box_button.setChecked(box_straighten.isChecked())
        )
        self.shared_boundary_box_straighten_button = box_button
        self.shape_dock.parentWidget().layout().insertWidget(3, box_button)

        detail_preset = QtGui.QAction("SAM2 细节优先（局部裁剪 + 细轮廓）", self)
        detail_preset.setToolTip(
            "加载 SAM2 后使用；开启局部裁剪并降低多边形轮廓简化程度，需先画包围框"
        )
        detail_preset.triggered.connect(lambda: _enable_sam2_detail_preset(self))
        self.menus.edit.addAction(detail_preset)

    def new_shape_with_shared_boundary(self):
        _cancel_vertex_tools(self)
        if self.shared_boundary_refine_action.isChecked():
            self.shared_boundary_refine_action.setChecked(False)
        shape = self.canvas.shapes[-1] if self.canvas.shapes else None
        can_resume = (
            shape is not None
            and shape.shape_type == "polygon"
            and shape.label not in SPECIAL_LABELS
            and self.canvas.drawing()
            and not self.canvas.is_auto_labeling
            and not self.canvas.is_magic_wand_mode
        )
        cancelled = False
        points = list(shape.points) if can_resume else []
        undo_history = list(self.canvas.shapes_backups)
        brush = can_resume and not self.actions.create_brush_polygon_mode.isEnabled()
        original_popup = self.label_dialog.pop_up

        def observe_popup(*args, **kwargs):
            nonlocal cancelled
            result = original_popup(*args, **kwargs)
            cancelled = not result[0]
            return result

        self.label_dialog.pop_up = observe_popup
        try:
            original_new_shape(self)
        finally:
            self.label_dialog.pop_up = original_popup
        if can_resume and cancelled:
            _resume_polygon_draft(self, shape, points, undo_history, brush=brush)
            return
        if shape is not None and shape.label and shape in self.canvas.shapes:
            _carve_widget(self, [shape])

    def finish_auto_with_shared_boundary(self):
        _cancel_vertex_tools(self)
        if self.shared_boundary_refine_action.isChecked():
            self.shared_boundary_refine_action.setChecked(False)
        candidates = [
            shape
            for shape in self.canvas.shapes
            if shape.label == "AUTOLABEL_OBJECT"
        ]
        original_finish_auto(self)
        _carve_widget(self, candidates)

    def undo_with_shared_boundary(self):
        _cancel_vertex_tools(self)
        if self.shared_boundary_refine_action.isChecked():
            self.shared_boundary_refine_action.setChecked(False)
        original_undo(self)

    def load_file_with_shared_boundary(self, *args, **kwargs):
        self.canvas._shared_boundary_middle_pan = None
        self.canvas._shared_boundary_paused_draft = None
        self.canvas._shared_boundary_zoom_padding = None
        self.canvas._shared_boundary_navigation_global = None
        self.canvas._shared_boundary_pointer_global = None
        self.canvas._shared_boundary_zoom_anchor = None
        _cancel_vertex_tools(self)
        action = getattr(self, "shared_boundary_refine_action", None)
        if action is not None and action.isChecked():
            action.setChecked(False)
        self._shared_boundary_list_shape = None
        button = getattr(self, "shared_boundary_deduct_button", None)
        if button is not None:
            button.setText("点下方类别名称，从它自身扣除重叠")
        return original_load_file(self, *args, **kwargs)

    LabelingWidget.__init__ = init_with_shared_boundary
    LabelingWidget.new_shape = new_shape_with_shared_boundary
    LabelingWidget.finish_auto_labeling_object = finish_auto_with_shared_boundary
    LabelingWidget.undo_shape_edit = undo_with_shared_boundary
    LabelingWidget.load_file = load_file_with_shared_boundary
    LabelingWidget._shared_boundary_installed = True
