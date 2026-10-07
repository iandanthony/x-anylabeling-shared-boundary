import os
import unittest

from shapely.geometry import Polygon
from shapely.ops import unary_union

from shared_boundary import (
    _annotation_geometry,
    _apply_straighten,
    _carve_widget,
    _deduct_from_list,
    _enable_sam2_detail_preset,
    _resolve_list_target,
    _StraightenClickFilter,
    _BoxStraightenFilter,
    _toggle_box_straighten,
    _start_refinement,
    _update_refinement,
    subtract_coordinates,
    straighten_vertex_span,
    selected_vertex_span,
    vertices_in_selection,
    transfer_shared_boundary,
)


class SharedBoundaryTests(unittest.TestCase):
    def test_polygon_selection_respects_concavity_boundary_and_invalid_region(self):
        selection = [(0, 0), (4, 0), (4, 4), (2, 2), (0, 4)]
        points = [(1, 1), (2, 3), (3, 3), (0, 2), (5, 2), (1, 1)]
        self.assertEqual(vertices_in_selection(points, selection), [0, 2, 3])
        with self.assertRaisesRegex(ValueError, "交叉"):
            vertices_in_selection(points, [(0, 0), (4, 4), (0, 4), (4, 0)])

    def test_box_selected_span_wraps_and_requires_single_run(self):
        ring = [(0, 0), (3, 0), (3, 3), (2, 4), (1, 4), (0, 3)]
        self.assertEqual(selected_vertex_span(ring + [ring[0]], [5, 0, 1]), [5, 0, 1])
        with self.assertRaisesRegex(ValueError, "不连续"):
            selected_vertex_span(ring, [0, 1, 3])
        with self.assertRaisesRegex(ValueError, "整个"):
            selected_vertex_span(ring, range(len(ring)))
        with self.assertRaisesRegex(ValueError, "至少三个"):
            selected_vertex_span(ring, [0, 1])

    def test_box_selected_arc_is_used_even_when_other_arc_is_shorter(self):
        # The selected detour is longer than the retained three-edge boundary.
        ring = [(4, 0), (4, 10), (3, 10), (3, 1),
                (1, 1), (1, 10), (0, 10), (0, 0)]
        span = selected_vertex_span(ring, range(7))
        result, removed = straighten_vertex_span(ring, span[0], span[-1], along_forward=True)
        self.assertEqual(removed, 5)
        self.assertEqual(result, [ring[i] for i in (0, 6, 7)])

    def test_polygon_selection_preview_enter_undo_and_cancel_with_real_canvas(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6 import QtCore, QtGui, QtWidgets
        from anylabeling.views.labeling.shape import Shape
        from anylabeling.views.labeling.widgets.canvas import Canvas

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        canvas = Canvas(parent=None)
        canvas.selection_changed.connect(lambda shapes: setattr(canvas, "selected_shapes", shapes))
        canvas.resize(300, 300)
        canvas.pixmap = QtGui.QPixmap(100, 100)
        canvas.pixmap.fill(QtGui.QColor("white"))
        canvas.scale = 2.0
        ring = [(10, 10), (60, 10), (60, 25), (45, 30), (60, 40), (60, 60), (10, 60)]
        shape = Shape(label="建筑废料", shape_type="polygon")
        shape.points = [QtCore.QPointF(x, y) for x, y in ring]
        shape.close()
        canvas.shapes = [shape]
        canvas.select_shapes([shape])
        canvas.store_shapes()
        action = QtGui.QAction()
        action.setCheckable(True)
        messages = []
        widget = type("Widget", (), {
            "canvas": canvas,
            "shared_boundary_box_straighten_action": action,
            "statusBar": lambda self: self,
            "showMessage": lambda self, message, timeout: messages.append(message),
            "set_dirty": lambda self: None,
        })()
        tool = _BoxStraightenFilter.create(widget)
        widget._shared_boundary_box_straighten_filter = tool
        canvas.installEventFilter(tool)
        action.toggled.connect(lambda enabled: _toggle_box_straighten(widget, enabled))
        action.setChecked(True)
        offset = canvas.offset_to_center()

        def position(x, y):
            return (QtCore.QPointF(x, y) + offset) * canvas.scale

        def mouse(kind, x, y, button, buttons):
            event = QtGui.QMouseEvent(kind, position(x, y), button, buttons,
                                     QtCore.Qt.KeyboardModifier.NoModifier)
            app.sendEvent(canvas, event)

        def click(x, y, kind=QtCore.QEvent.Type.MouseButtonPress):
            mouse(kind, x, y, QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.LeftButton)
            mouse(QtCore.QEvent.Type.MouseButtonRelease, x, y,
                  QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.MouseButton.NoButton)

        def key(code):
            app.sendEvent(canvas, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                                code, QtCore.Qt.KeyboardModifier.NoModifier))

        # Nonzero centering offset and zoom verify image mapping.
        for x, y in [(40, 5), (65, 5), (65, 65), (40, 65)]:
            click(x, y)
        key(QtCore.Qt.Key.Key_Backspace)
        self.assertEqual(len(tool.region), 3)
        click(40, 65)
        click(40, 5)  # click first corner to close without modifying the label
        self.assertEqual(tool.span, [1, 2, 3, 4, 5])
        self.assertEqual(len(shape.points), 7)  # preview does not modify labels
        self.assertIn("Enter", messages[-1])
        self.assertTrue(tool.region_closed)
        tool.overlay.grab()  # exercise preview painting, including endpoint markers
        key(QtCore.Qt.Key.Key_Return)
        self.assertFalse(action.isChecked())
        self.assertEqual(len(canvas.shapes[0].points), 4)
        self.assertEqual(len(canvas.shapes_backups), 2)
        canvas.restore_shape()
        self.assertEqual([(p.x(), p.y()) for p in canvas.shapes[0].points], ring)
        canvas.select_shapes([canvas.shapes[0]])
        action.setChecked(True)
        # Enter first closes the selection and previews; only next Enter commits.
        for x, y in [(40, 5), (65, 5), (65, 65), (40, 65)]:
            click(x, y)
        key(QtCore.Qt.Key.Key_Return)
        self.assertTrue(tool.region_closed)
        self.assertEqual(len(canvas.shapes[0].points), 7)
        # A double-click after closure must not erase the preview.
        click(40, 65, QtCore.QEvent.Type.MouseButtonDblClick)
        self.assertEqual(tool.span, [1, 2, 3, 4, 5])
        mouse(QtCore.QEvent.Type.MouseButtonPress, 65, 65,
              QtCore.Qt.MouseButton.RightButton, QtCore.Qt.MouseButton.RightButton)
        mouse(QtCore.QEvent.Type.MouseButtonRelease, 65, 65,
              QtCore.Qt.MouseButton.RightButton, QtCore.Qt.MouseButton.NoButton)
        self.assertFalse(action.isChecked())
        self.assertFalse(tool.swallow_release)
        self.assertEqual(len(canvas.shapes[0].points), 7)
        action.setChecked(True)
        for x, y in [(40, 5), (65, 5), (65, 65)]:
            click(x, y)
        click(40, 65, QtCore.QEvent.Type.MouseButtonDblClick)
        self.assertTrue(tool.region_closed)
        self.assertEqual(tool.span, [1, 2, 3, 4, 5])
        key(QtCore.Qt.Key.Key_Escape)
        self.assertFalse(action.isChecked())
        canvas.close()

    def test_straighten_clicks_remove_vertices_and_release_is_consumed(self):
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6 import QtCore, QtGui, QtWidgets
        from anylabeling.views.labeling.shape import Shape

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        shape = Shape(label="建筑废料", shape_type="polygon")
        ring = [(0, 0), (3, 0), (3, 1), (2, 1), (3, 2), (3, 3), (0, 3)]
        shape.points = [QtCore.QPointF(x, y) for x, y in ring]

        class Canvas(QtWidgets.QWidget):
            scale = 1.0

            def __init__(self):
                super().__init__()
                self.shapes = [shape]
                self.snapshots = []
                self.shape_moved = type("Signal", (), {"emit": lambda self: None})()

            def transform_pos(self, point):
                return point

            def store_shapes(self):
                self.snapshots.append(shape.copy())

        canvas = Canvas()
        action = QtGui.QAction()
        action.setCheckable(True)
        action.setChecked(True)
        widget = type("Widget", (), {
            "canvas": canvas,
            "shared_boundary_straighten_action": action,
            "statusBar": lambda self: self,
            "showMessage": lambda self, message, timeout: None,
            "set_dirty": lambda self: None,
        })()
        click_filter = _StraightenClickFilter.create(widget)
        click_filter.target = shape
        canvas.installEventFilter(click_filter)
        for x, y in [(3, 0), (3, 3)]:
            for event_type, buttons in [
                (QtCore.QEvent.Type.MouseButtonPress, QtCore.Qt.MouseButton.LeftButton),
                (QtCore.QEvent.Type.MouseButtonRelease, QtCore.Qt.MouseButton.NoButton),
            ]:
                event = QtGui.QMouseEvent(
                    event_type,
                    QtCore.QPointF(x, y),
                    QtCore.Qt.MouseButton.LeftButton,
                    buttons,
                    QtCore.Qt.KeyboardModifier.NoModifier,
                )
                app.sendEvent(canvas, event)
        self.assertFalse(action.isChecked())
        self.assertFalse(click_filter.swallow_release)
        self.assertEqual(len(shape.points), 4)
        self.assertEqual(len(canvas.snapshots), 1)

    def test_straighten_keeps_endpoints_and_removes_shorter_arc(self):
        ring = [(0, 0), (3, 0), (3, 1), (2, 1), (3, 2), (3, 3), (0, 3)]
        result, removed = straighten_vertex_span(ring + [ring[0]], 1, 5)
        self.assertEqual(removed, 3)
        self.assertEqual(result, [(0, 0), (3, 0), (3, 3), (0, 3), (0, 0)])
        reverse, reverse_removed = straighten_vertex_span(ring, 5, 1)
        self.assertEqual(reverse_removed, 3)
        self.assertEqual(reverse, result[:-1])
        self.assertAlmostEqual(Polygon(reverse).area, 9)

    def test_straighten_requires_nonadjacent_vertices(self):
        ring = [(0, 0), (3, 0), (3, 3), (0, 3)]
        with self.assertRaises(ValueError):
            straighten_vertex_span(ring, 0, 1)

    def test_straighten_preserves_unrelated_existing_sam_loop(self):
        ring = [(0, 0), (1, 0), (1, 1), (2, 1), (2, 0), (1, 0),
                (4, 0), (4, 1), (3.5, 1.5), (4, 2), (4, 4), (0, 4)]
        self.assertFalse(Polygon(ring).is_valid)
        result, removed = straighten_vertex_span(ring, 6, 10)
        self.assertEqual(removed, 3)
        self.assertEqual(result, ring[:7] + ring[10:])
        self.assertIsNotNone(_annotation_geometry(result))

    def test_straighten_rejects_new_crossing_even_with_existing_loop(self):
        ring = [(0, 0), (1, 0), (1, 1), (2, 1), (2, 0), (1, 0),
                (6, 0), (6, 6), (5, 6), (5, 2), (4, 2), (4, 6),
                (3, 6), (3, 2), (2, 2), (2, 6), (0, 6)]
        self.assertFalse(Polygon(ring).is_valid)
        with self.assertRaisesRegex(ValueError, "相交"):
            straighten_vertex_span(ring, 6, 15)

    def test_straighten_records_undo_and_emits_shape_move(self):
        from PyQt6.QtCore import QPointF
        from anylabeling.views.labeling.shape import Shape

        shape = Shape(label="建筑废料", shape_type="polygon")
        ring = [(0, 0), (3, 0), (3, 1), (2, 1), (3, 2), (3, 3), (0, 3)]
        shape.points = [QPointF(x, y) for x, y in ring]

        class Signal:
            calls = 0

            def emit(self):
                self.calls += 1

        class Canvas:
            def __init__(self):
                self.shape_moved = Signal()
                self.snapshots = []

            def store_shapes(self):
                self.snapshots.append(shape.copy())

            def update(self):
                pass

        canvas = Canvas()
        widget = type("Widget", (), {
            "canvas": canvas,
            "set_dirty": lambda self: None,
        })()
        self.assertEqual(_apply_straighten(widget, shape, 1, 5), 3)
        self.assertEqual(len(canvas.snapshots), 1)
        self.assertEqual(canvas.shape_moved.calls, 1)
        self.assertEqual(len(shape.points), 4)

    def test_sam2_detail_preset_enables_crop_and_finer_outline(self):
        class SegmentAnything2:
            pass

        class Slider:
            value = 10

            def setValue(self, value):
                self.value = value

        class Button:
            checked = False

            def isChecked(self):
                return self.checked

            def click(self):
                self.checked = True

        panel = type("Panel", (), {})()
        panel.model_manager = type("Manager", (), {
            "loaded_model_config": {"model": SegmentAnything2()}
        })()
        panel.mask_fineness_slider = Slider()
        panel.button_cropping = Button()
        widget = type("Widget", (), {
            "auto_labeling_widget": panel,
            "statusBar": lambda self: self,
            "showMessage": lambda self, message, timeout: None,
        })()
        self.assertTrue(_enable_sam2_detail_preset(widget))
        self.assertEqual(panel.mask_fineness_slider.value, 3)
        self.assertTrue(panel.button_cropping.checked)

    def test_stale_shapes_row_recovers_the_live_selected_polygon(self):
        from PyQt6.QtCore import QPointF
        from anylabeling.views.labeling.shape import Shape

        live = Shape(label="建筑废料", shape_type="polygon")
        live.points = [QPointF(x, y) for x, y in [(0, 0), (2, 0), (2, 2), (0, 2)]]
        stale = live.copy()
        canvas = type("Canvas", (), {"shapes": [live], "selected_shapes": [live]})()
        widget = type("Widget", (), {
            "canvas": canvas,
            "_shared_boundary_list_shape": stale,
        })()
        self.assertIs(_resolve_list_target(widget), live)

    def test_self_crossing_reference_keeps_both_visible_regions(self):
        bow_tie = [(0, 0), (2, 2), (0, 2), (2, 0)]
        repaired = _annotation_geometry(bow_tie)
        self.assertIsNotNone(repaired)
        self.assertAlmostEqual(repaired.area, 2)
        target = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        self.assertAlmostEqual(target.intersection(repaired).area, 0.5)
        self.assertAlmostEqual(target.difference(repaired).area, 0.5)

    def test_shared_edge_and_area(self):
        old = [(0, 0), (10, 0), (10, 10), (0, 10)]
        new = [(5, -1), (12, -1), (12, 11), (5, 11)]
        rings = subtract_coordinates(old, new)
        self.assertEqual(len(rings), 1)
        remainder = Polygon(rings[0])
        self.assertEqual(remainder.area, 50)
        self.assertEqual(remainder.intersection(Polygon(new)).area, 0)
        self.assertEqual(remainder.boundary.intersection(Polygon(new).boundary).length, 10)

    def test_enclosed_new_region_is_split_without_losing_area(self):
        old = [(0, 0), (10, 0), (10, 10), (0, 10)]
        new = [(3, 3), (7, 3), (7, 7), (3, 7)]
        rings = subtract_coordinates(old, new)
        pieces = [Polygon(ring) for ring in rings]
        self.assertGreaterEqual(len(pieces), 2)
        self.assertTrue(all(not piece.interiors for piece in pieces))
        self.assertAlmostEqual(unary_union(pieces).area, 84)
        self.assertAlmostEqual(unary_union(pieces).intersection(Polygon(new)).area, 0)

    def test_nonoverlap_and_invalid_are_unchanged(self):
        old = [(0, 0), (1, 0), (1, 1), (0, 1)]
        self.assertIsNone(subtract_coordinates(old, [(2, 2), (3, 2), (3, 3)]))
        self.assertIsNone(subtract_coordinates(old, [(0, 0), (1, 1), (0, 1), (1, 0)]))

    def test_fully_covered_old_region_is_removed(self):
        old = [(1, 1), (2, 1), (2, 2), (1, 2)]
        new = [(0, 0), (3, 0), (3, 3), (0, 3)]
        self.assertEqual(subtract_coordinates(old, new), [])

    def test_refinement_shrink_transfers_area_to_neighbor(self):
        edited = Polygon([(5, 0), (10, 0), (10, 10), (5, 10)])
        neighbor = Polygon([(0, 0), (5, 0), (5, 10), (0, 10)])
        domain = edited.union(neighbor)
        smaller = [(7, 0), (10, 0), (10, 10), (7, 10)]
        next_domain, rings = transfer_shared_boundary(domain, smaller)
        new_neighbor = unary_union([Polygon(ring) for ring in rings])
        self.assertAlmostEqual(new_neighbor.area, 70)
        self.assertAlmostEqual(new_neighbor.intersection(Polygon(smaller)).area, 0)
        self.assertAlmostEqual(new_neighbor.union(Polygon(smaller)).area, 100)
        self.assertTrue(next_domain.equals(domain))
        self.assertEqual(new_neighbor.boundary.intersection(Polygon(smaller).boundary).length, 10)

    def test_refinement_growth_makes_neighbor_retreat(self):
        domain = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
        larger = [(3, 0), (10, 0), (10, 10), (3, 10)]
        _, rings = transfer_shared_boundary(domain, larger)
        new_neighbor = unary_union([Polygon(ring) for ring in rings])
        self.assertAlmostEqual(new_neighbor.area, 30)
        self.assertAlmostEqual(new_neighbor.intersection(Polygon(larger)).area, 0)

    def test_widget_updates_shapes_list_and_undo_snapshot(self):
        from PyQt6.QtCore import QPointF
        from anylabeling.views.labeling.shape import Shape

        def shape(label, coords):
            result = Shape(label=label, shape_type="polygon")
            result.points = [QPointF(x, y) for x, y in coords]
            result.close()
            return result

        class Canvas:
            def __init__(self, shapes):
                self.shapes = shapes
                self.shapes_backups = [[shapes[0].copy()], [s.copy() for s in shapes]]
                self.selected_shapes = []
                self.updated = False

            def update(self):
                self.updated = True

            def store_shapes(self):
                self.shapes_backups.append([s.copy() for s in self.shapes])

        class Widget:
            def __init__(self, shapes):
                self.canvas = Canvas(shapes)
                self.shared_boundary_action = self
                self.listed = list(shapes)
                self.dirty = False

            def isChecked(self):
                return True

            def add_label(self, shape):
                self.listed.append(shape)

            def remove_labels(self, shapes):
                for shape in shapes:
                    self.listed.remove(shape)

            def _refresh_shape_filters(self):
                pass

            def set_dirty(self):
                self.dirty = True

            def statusBar(self):
                return self

            def showMessage(self, message, timeout):
                self.message = message

        old = shape("工程渣土", [(0, 0), (10, 0), (10, 10), (0, 10)])
        new = shape("装修垃圾", [(5, -1), (12, -1), (12, 11), (5, 11)])
        widget = Widget([old, new])
        self.assertTrue(_carve_widget(widget, [new]))
        self.assertTrue(widget.canvas.updated and widget.dirty)
        self.assertEqual(len(widget.canvas.shapes), len(widget.listed))
        self.assertEqual(len(widget.canvas.shapes_backups), 2)
        self.assertEqual(widget.canvas.shapes_backups[-1][0].points, old.points)
        self.assertAlmostEqual(Polygon([(p.x(), p.y()) for p in old.points]).area, 100)
        self.assertAlmostEqual(Polygon([(p.x(), p.y()) for p in new.points]).area, 34)
        self.assertEqual(widget.canvas.shapes_backups[-1][1].points, new.points)

    def test_widget_preserves_locked_shapes(self):
        widget, old, new = self._automatic_fixture()
        old.locked = True
        original = list(old.points)
        self.assertTrue(_carve_widget(widget, [new]))
        self.assertEqual(old.points, original)
        self.assertTrue(old.locked)
        self.assertAlmostEqual(self._shape_geometry(new).area, 20)

    @staticmethod
    def _shape_geometry(shape):
        return Polygon([(p.x(), p.y()) for p in shape.points])

    def _automatic_fixture(self, new_points=None):
        widget, old, new = self._deduction_fixture(second_points=new_points)
        widget.shared_boundary_action = type(
            "Action", (), {"isChecked": lambda self: True}
        )()
        return widget, old, new

    def test_auto_clip_removes_fully_covered_new_shape_only(self):
        widget, old, new = self._automatic_fixture([(1, 1), (2, 1), (2, 2), (1, 2)])
        old_points = list(old.points)
        widget.canvas.selected_shapes = [new]
        self.assertTrue(_carve_widget(widget, [new]))
        self.assertEqual(widget.canvas.shapes, [old])
        self.assertEqual(widget.listed, [old])
        self.assertEqual(widget.canvas.selected_shapes, [])
        self.assertIsNone(widget._shared_boundary_list_shape)
        self.assertEqual(old.points, old_points)
        self.assertEqual(len(widget.canvas.shapes_backups), 2)
        self.assertEqual(len(widget.canvas.shapes_backups[-1]), 1)
        self.assertIn("完全被覆盖", widget.message)

    def test_auto_clip_splits_new_shape_and_preserves_metadata(self):
        from PyQt6.QtCore import QPointF

        widget, old, new = self._automatic_fixture([(0, 0), (10, 0), (10, 10), (0, 10)])
        old.points = [QPointF(x, y) for x, y in [(4, -1), (6, -1), (6, 11), (4, 11)]]
        old_before = list(old.points)
        new.group_id = 17
        new.description = "保留新区域属性"
        new.flags = {"checked": True}
        self.assertTrue(_carve_widget(widget, [new]))
        pieces = [s for s in widget.canvas.shapes if s is not old]
        self.assertEqual(len(pieces), 2)
        self.assertEqual(len(widget.listed), 3)
        result = unary_union([self._shape_geometry(s) for s in pieces])
        self.assertAlmostEqual(result.area, 80)
        self.assertAlmostEqual(result.intersection(self._shape_geometry(old)).area, 0)
        self.assertEqual(old.points, old_before)
        self.assertTrue(all(s.group_id == 17 and s.description == new.description
                            and s.flags == new.flags for s in pieces))
        self.assertEqual(len(widget.canvas.shapes_backups[-1]), 3)

    def test_auto_clip_enclosed_old_region_leaves_hole_free_new_parts(self):
        from PyQt6.QtCore import QPointF

        widget, old, new = self._automatic_fixture([(0, 0), (10, 0), (10, 10), (0, 10)])
        old.points = [QPointF(x, y) for x, y in [(3, 3), (7, 3), (7, 7), (3, 7)]]
        before = list(old.points)
        self.assertTrue(_carve_widget(widget, [new]))
        polygons = [self._shape_geometry(s) for s in widget.canvas.shapes if s is not old]
        self.assertGreaterEqual(len(polygons), 2)
        self.assertTrue(all(p.is_valid and not p.interiors for p in polygons))
        self.assertAlmostEqual(unary_union(polygons).area, 84)
        self.assertAlmostEqual(unary_union(polygons).intersection(self._shape_geometry(old)).area, 0)
        self.assertEqual(old.points, before)

    def test_auto_clip_subtracts_union_of_multiple_existing_labels(self):
        from PyQt6.QtCore import QPointF

        widget, old, new = self._automatic_fixture([(0, 0), (14, 0), (14, 10), (0, 10)])
        other = old.copy()
        other.label = "拆除垃圾"
        other.points = [QPointF(x, y) for x, y in [(8, 0), (12, 0), (12, 10), (8, 10)]]
        widget.canvas.shapes.insert(1, other)
        widget.listed.insert(1, other)
        before = [list(s.points) for s in (old, other)]
        self.assertTrue(_carve_widget(widget, [new]))
        self.assertAlmostEqual(self._shape_geometry(new).area, 20)
        self.assertEqual([list(s.points) for s in (old, other)], before)
        self.assertEqual(self._shape_geometry(new).bounds, (12, 0, 14, 10))

    def test_auto_clip_disabled_same_class_touching_and_nonpolygon_are_unchanged(self):
        widget, old, new = self._automatic_fixture()
        before = list(new.points)
        widget.shared_boundary_action = type("Action", (), {"isChecked": lambda self: False})()
        self.assertFalse(_carve_widget(widget, [new]))
        self.assertEqual(new.points, before)
        widget.shared_boundary_action = type("Action", (), {"isChecked": lambda self: True})()
        old.label = new.label
        self.assertFalse(_carve_widget(widget, [new]))
        old.label = "工程渣土"
        old.shape_type = "rectangle"
        self.assertFalse(_carve_widget(widget, [new]))
        old.shape_type = "polygon"
        old.label = "AUTOLABEL_OBJECT"
        self.assertFalse(_carve_widget(widget, [new]))
        widget, old, new = self._automatic_fixture([(10, 0), (12, 0), (12, 10), (10, 10)])
        before = list(new.points)
        self.assertFalse(_carve_widget(widget, [new]))
        self.assertEqual(new.points, before)

    def test_auto_clip_locked_new_shape_is_unchanged(self):
        widget, old, new = self._automatic_fixture()
        before = [list(s.points) for s in (old, new)]
        new.locked = True
        self.assertFalse(_carve_widget(widget, [new]))
        self.assertEqual([list(s.points) for s in (old, new)], before)
        self.assertIn("锁定", widget.message)

    def test_auto_clip_batch_candidates_do_not_become_existing_references(self):
        widget, old, new = self._automatic_fixture()
        second = new.copy()
        second.label = "拆除垃圾"
        widget.canvas.shapes.append(second)
        widget.listed.append(second)
        self.assertTrue(_carve_widget(widget, [new, second]))
        self.assertIn(new, widget.canvas.shapes)
        self.assertIn(second, widget.canvas.shapes)
        self.assertAlmostEqual(self._shape_geometry(new).area, 20)
        self.assertTrue(self._shape_geometry(new).equals(self._shape_geometry(second)))
        self.assertAlmostEqual(self._shape_geometry(old).area, 100)

    def test_explicit_reverse_tool_still_clips_other_regions(self):
        widget, old, new = self._automatic_fixture()
        before = list(new.points)
        self.assertTrue(_carve_widget(widget, [new], force=True, preserve_existing=False))
        self.assertAlmostEqual(self._shape_geometry(old).area, 50)
        self.assertEqual(new.points, before)

    def test_linked_refinement_updates_neighbor_shape(self):
        from PyQt6.QtCore import QPointF
        from anylabeling.views.labeling.shape import Shape

        def shape(label, coords):
            result = Shape(label=label, shape_type="polygon")
            result.points = [QPointF(x, y) for x, y in coords]
            result.close()
            return result

        old = shape("工程渣土", [(0, 0), (5, 0), (5, 10), (0, 10)])
        new = shape("装修垃圾", [(5, 0), (10, 0), (10, 10), (5, 10)])

        class Canvas:
            shapes = [old, new]
            selected_shapes = [new]
            shapes_backups = [[old.copy()], [old.copy(), new.copy()]]

            def update(self):
                pass

        class Action:
            def __init__(self):
                self.checked = True

            def isChecked(self):
                return self.checked

            def setChecked(self, value):
                self.checked = value

        class Widget:
            image_path = "test.jpg"

            def __init__(self):
                self.canvas = Canvas()
                self.shared_boundary_refine_action = Action()
                self._shared_boundary_session = None
                self.listed = [old, new]
                self.dirty = False

            def statusBar(self):
                return self

            def showMessage(self, message, timeout):
                self.message = message

            def remove_labels(self, shapes):
                for item in shapes:
                    self.listed.remove(item)

            def add_label(self, item):
                self.listed.append(item)

            def _refresh_shape_filters(self):
                pass

            def set_dirty(self):
                self.dirty = True

        widget = Widget()
        _start_refinement(widget)
        self.assertIsNotNone(widget._shared_boundary_session)
        new.points = [QPointF(x, y) for x, y in [(7, 0), (10, 0), (10, 10), (7, 10)]]
        self.assertTrue(_update_refinement(widget))
        neighbor = widget._shared_boundary_session["neighbor_parts"][0]
        self.assertAlmostEqual(Polygon([(p.x(), p.y()) for p in neighbor.points]).area, 70)
        self.assertEqual(len(widget.listed), len(widget.canvas.shapes))
        self.assertTrue(widget.dirty)

    def _deduction_fixture(self, second_label="装修垃圾", second_points=None):
        from PyQt6.QtCore import QPointF
        from anylabeling.views.labeling.shape import Shape

        def shape(label, coords):
            result = Shape(label=label, shape_type="polygon")
            result.points = [QPointF(x, y) for x, y in coords]
            result.close()
            return result

        soil = shape("工程渣土", [(0, 0), (10, 0), (10, 10), (0, 10)])
        debris = shape(second_label, second_points or [(5, 0), (12, 0), (12, 10), (5, 10)])

        class Canvas:
            shapes = [soil, debris]
            selected_shapes = []  # Hover has already vanished.
            shapes_backups = [[soil.copy()], [soil.copy(), debris.copy()]]

            def update(self):
                pass

            def store_shapes(self):
                self.shapes_backups.append([s.copy() for s in self.shapes])

        class Widget:
            def __init__(self):
                self.canvas = Canvas()
                self._shared_boundary_list_shape = debris
                self.listed = [soil, debris]
                self.shared_boundary_deduct_button = type(
                    "Button", (), {"setText": lambda self, text: None}
                )()

            def remove_labels(self, shapes):
                for item in shapes:
                    self.listed.remove(item)

            def add_label(self, item):
                self.listed.append(item)

            def _refresh_shape_filters(self):
                pass

            def set_dirty(self):
                pass

            def statusBar(self):
                return self

            def showMessage(self, message, timeout):
                self.message = message

        widget = Widget()
        return widget, soil, debris

    def test_same_class_deduction_preserves_reference_and_ignores_other_classes(self):
        widget, soil, debris = self._deduction_fixture(second_label="工程渣土")
        other = soil.copy()
        other.label = "装修垃圾"
        widget.canvas.shapes.append(other)
        widget.listed.append(other)
        soil.locked = True  # References may be locked; they are not modified.
        soil_points = list(soil.points)
        other_points = list(other.points)
        self.assertTrue(_deduct_from_list(widget, same_class=True))
        self.assertEqual(soil.points, soil_points)
        self.assertEqual(other.points, other_points)
        self.assertAlmostEqual(Polygon([(p.x(), p.y()) for p in debris.points]).area, 20)
        self.assertAlmostEqual(Polygon([(p.x(), p.y()) for p in soil.points])
                               .intersection(Polygon([(p.x(), p.y()) for p in debris.points])).area, 0)
        self.assertEqual(len(widget.canvas.shapes_backups), 3)

    def test_same_class_deduction_skips_same_group_and_locked_target(self):
        widget, soil, debris = self._deduction_fixture(second_label="工程渣土")
        soil.group_id = debris.group_id = 5
        self.assertFalse(_deduct_from_list(widget, same_class=True))
        self.assertIn("Group ID", widget.message)
        self.assertEqual(len(widget.canvas.shapes_backups), 2)
        debris.group_id = 6
        debris.locked = True
        self.assertFalse(_deduct_from_list(widget, same_class=True))
        self.assertIn("锁定", widget.message)
        debris.locked = False
        self.assertTrue(_deduct_from_list(widget, same_class=True))

    def test_same_class_fully_covered_object_is_removed_with_undo_snapshot(self):
        widget, soil, debris = self._deduction_fixture(
            second_label="工程渣土", second_points=[(1, 1), (2, 1), (2, 2), (1, 2)])
        self.assertTrue(_deduct_from_list(widget, same_class=True))
        self.assertEqual(widget.canvas.shapes, [soil])
        self.assertEqual(widget.listed, [soil])
        self.assertEqual(len(widget.canvas.shapes_backups[-2]), 2)
        self.assertEqual(len(widget.canvas.shapes_backups[-1]), 1)

    def test_shapes_row_deduction_does_not_need_canvas_selection(self):
        widget, soil, debris = self._deduction_fixture()
        self.assertTrue(_deduct_from_list(widget))
        self.assertAlmostEqual(
            Polygon([(p.x(), p.y()) for p in soil.points]).area, 100
        )
        self.assertAlmostEqual(
            Polygon([(p.x(), p.y()) for p in debris.points]).area, 20
        )
        self.assertAlmostEqual(
            Polygon([(p.x(), p.y()) for p in debris.points])
            .boundary.intersection(Polygon([(p.x(), p.y()) for p in soil.points]).boundary)
            .length,
            10,
        )
        self.assertEqual(len(widget.canvas.shapes_backups), 3)
        self.assertEqual(len(widget.listed), len(widget.canvas.shapes))


if __name__ == "__main__":
    unittest.main()
