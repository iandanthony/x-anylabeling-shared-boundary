"""Open the real app briefly offscreen and assert the new mode is present."""

import os
import runpy
import sys
import copy
import json
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
test_work = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
sys.argv = ["launch.py", "--no-auto-update-check", "--work-dir", test_work.name]

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402


original_exec = QtWidgets.QApplication.exec


def check_existing_priority(widget):
    """Exercise real completion, JSON saving and Undo without loading a model."""
    from anylabeling.views.labeling.shape import Shape
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    def shape(label, coordinates):
        item = Shape(label=label, shape_type="polygon")
        item.points = [QtCore.QPointF(x, y) for x, y in coordinates]
        item.close()
        return item

    def geometry(item):
        return Polygon([(p.x(), p.y()) for p in item.points])

    original_popup = widget.label_dialog.pop_up
    widget.label_dialog.pop_up = lambda *a, **k: ("装修垃圾", {}, None, "", False, [])
    widget._config["display_label_popup"] = True
    widget._config["auto_use_last_label"] = False
    try:
        for mode in ("manual", "auto", "covered", "split", "enclosed"):
            image_path = Path(test_work.name) / f"{mode}.png"
            image = QtGui.QImage(20, 20, QtGui.QImage.Format.Format_RGB32)
            image.fill(QtCore.Qt.GlobalColor.white)
            assert image.save(str(image_path))
            widget.load_file(str(image_path))
            old_coords = ([(4, 0), (6, 0), (6, 10), (4, 10)] if mode == "split"
                          else [(3, 3), (7, 3), (7, 7), (3, 7)] if mode == "enclosed"
                          else [(0, 0), (10, 0), (10, 10), (0, 10)])
            old = shape("工程渣土", old_coords)
            old.locked = True
            widget.load_shapes([old])
            before = list(old.points)
            coordinates = ([(1, 1), (2, 1), (2, 2), (1, 2)] if mode == "covered"
                           else [(0, 0), (10, 0), (10, 10), (0, 10)] if mode in ("split", "enclosed")
                           else [(5, 0), (12, 0), (12, 10), (5, 10)])
            new = shape("AUTOLABEL_OBJECT" if mode == "auto" else None, coordinates)
            if mode == "auto":
                widget.canvas.shapes.append(new)
                widget.canvas.store_shapes()
                new.cache_label = "装修垃圾"
                new.cache_description = ""
                widget.add_label(new)
                widget.finish_auto_labeling_object()
            else:
                widget.canvas.current = new
                widget.canvas.finalise()
            assert old.points == before and old.locked
            if mode == "covered":
                assert widget.canvas.shapes == [old]
            else:
                result = unary_union([geometry(s) for s in widget.canvas.shapes if s is not old])
                assert result.area == {"split": 80, "enclosed": 84}.get(mode, 20)
                assert result.intersection(geometry(old)).area == 0
                if mode in ("manual", "auto"):
                    assert result.boundary.intersection(geometry(old).boundary).length == 10
            output = Path(test_work.name) / f"{mode}.json"
            assert widget.save_labels(str(output))
            saved = json.loads(output.read_text(encoding="utf-8"))
            saved_old = next(s for s in saved["shapes"] if s["label"] == "工程渣土")
            assert saved_old["points"] == [[p.x(), p.y()] for p in before]
            assert len(saved["shapes"]) == len(widget.canvas.shapes)
            assert len(widget.canvas.shapes_backups) == 2
            widget.undo_shape_edit()
            assert len(widget.canvas.shapes) == 1
            restored = widget.canvas.shapes[0]
            assert restored.label == "工程渣土" and restored.points == before and restored.locked
            print(f"existing priority: {mode} completion, JSON and Undo passed")
    finally:
        widget.label_dialog.pop_up = original_popup


def check_cancelled_drawing(widget):
    """Close the real label dialog, continue drawing, then confirm or discard."""
    from PyQt6 import QtTest
    from anylabeling.views.labeling.shape import Shape
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    for mode, dismissal in (("polygon", "close"), ("brush", "close"),
                            ("polygon", "cancel"), ("brush", "escape")):
        image_path = Path(test_work.name) / f"cancel-{mode}-{dismissal}.png"
        image = QtGui.QImage(100, 100, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        assert image.save(str(image_path))
        widget.load_file(str(image_path))
        old = Shape(label="工程渣土", shape_type="polygon")
        old.points = [QtCore.QPointF(x, y) for x, y in [(0, 0), (10, 0), (10, 10), (0, 10)]]
        old.close()
        widget.load_shapes([old])
        before = list(old.points)
        widget.unique_label_list.clearSelection()
        if mode == "brush":
            widget.toggle_brush_polygon_mode()
        else:
            widget.toggle_draw_mode(False, create_mode="polygon")
        canvas = widget.canvas
        pending = Shape(shape_type="polygon")
        pending.points = [QtCore.QPointF(x, y) for x, y in [(5, 0), (12, 0), (12, 10), (5, 10)]]
        kept_points = list(pending.points)
        # The press before a double click adds a duplicate; Canvas removes it.
        pending.points.append(QtCore.QPointF(pending.points[-1]))
        canvas.current = pending
        canvas.line.points = [pending[-1], pending[0]]

        def dismiss():
            assert widget.label_dialog.isVisible()
            if dismissal == "close":
                widget.label_dialog.close()
            elif dismissal == "cancel":
                widget.label_dialog.button_box.button(
                    QtWidgets.QDialogButtonBox.StandardButton.Cancel).click()
            else:
                QtTest.QTest.keyClick(widget.label_dialog, QtCore.Qt.Key.Key_Escape)

        QtCore.QTimer.singleShot(20, dismiss)
        double_click = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseButtonDblClick, QtCore.QPointF(10, 10),
            QtCore.QPointF(10, 10), QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.MouseButton.LeftButton, QtCore.Qt.KeyboardModifier.NoModifier)
        canvas.mouseDoubleClickEvent(double_click)
        assert canvas.current is pending and pending.points == kept_points
        assert not pending.is_closed() and pending.label is None
        assert canvas.drawing() and canvas._brush_drawing == (mode == "brush")
        assert canvas.shapes == [old] and old.points == before
        assert len(canvas.shapes_backups) == 1
        assert widget.actions.undo_last_point.isEnabled()
        assert not widget.actions.edit_mode.isEnabled()

        next_point = QtCore.QPointF(2, 15)
        screen_point = (next_point + canvas.offset_to_center()) * canvas.scale
        event_type = (QtCore.QEvent.Type.MouseMove if mode == "brush"
                      else QtCore.QEvent.Type.MouseButtonPress)
        button = (QtCore.Qt.MouseButton.NoButton if mode == "brush"
                  else QtCore.Qt.MouseButton.LeftButton)
        continued = QtGui.QMouseEvent(event_type, screen_point, screen_point, button,
                                     button, QtCore.Qt.KeyboardModifier.NoModifier)
        if mode == "brush":
            canvas.mouseMoveEvent(continued)
        else:
            canvas.mousePressEvent(continued)
        assert len(pending.points) == len(kept_points) + 1
        assert pending.points[:len(kept_points)] == kept_points
        if dismissal == "escape":
            # Esc in the canvas is still the explicit way to abandon a draft.
            QtTest.QTest.keyClick(canvas, QtCore.Qt.Key.Key_Escape)
            assert canvas.current is None and canvas.shapes == [old]
        else:
            expected = Polygon([(p.x(), p.y()) for p in pending.points]).difference(
                Polygon([(p.x(), p.y()) for p in old.points]))

            def confirm():
                widget.label_dialog.edit.setText("装修垃圾")
                widget.label_dialog.button_box.button(
                    QtWidgets.QDialogButtonBox.StandardButton.Ok).click()

            QtCore.QTimer.singleShot(20, confirm)
            QtTest.QTest.keyClick(canvas, QtCore.Qt.Key.Key_Return)
            assert canvas.current is None and len(canvas.shapes) >= 2
            actual = unary_union([
                Polygon([(p.x(), p.y()) for p in item.points])
                for item in canvas.shapes if item is not old
            ])
            assert actual.equals(expected) and old.points == before
            output = image_path.with_suffix(".json")
            assert widget.save_labels(str(output))
            assert len(json.loads(output.read_text(encoding="utf-8"))["shapes"]) == len(canvas.shapes)
            widget.undo_shape_edit()
            assert len(canvas.shapes) == 1 and canvas.shapes[0].points == before
        print(f"cancel dialog: {mode}/{dismissal}, vertices and continued drawing passed")


def check_brush_zoom(widget):
    """Measure real scroll-area anchoring and reject navigation-only points."""
    from anylabeling.views.labeling.shape import Shape

    for name, width, height in (("landscape", 2000, 400),
                                ("portrait", 400, 2000),
                                ("edge", 1600, 900),
                                ("panned", 2400, 1800)):
        image_path = Path(test_work.name) / f"zoom-{name}.png"
        image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        assert image.save(str(image_path))
        widget.load_file(str(image_path))
        widget.set_fit_window()
        QtWidgets.QApplication.processEvents()
        canvas = widget.canvas
        if name == "panned":
            widget.set_zoom(160)
            widget.set_scroll(QtCore.Qt.Orientation.Horizontal, 900)
            widget.set_scroll(QtCore.Qt.Orientation.Vertical, 700)
            QtWidgets.QApplication.processEvents()
            viewport = widget._canvas_scroll_area.viewport()
            local = canvas.mapFrom(viewport, QtCore.QPoint(viewport.width() // 2,
                                                          viewport.height() // 2))
            anchor = canvas.transform_pos(QtCore.QPointF(local))
        elif name == "edge":
            anchor = QtCore.QPointF(width * 0.02, height * 0.025)
        else:
            anchor = QtCore.QPointF(width * 0.63, height * 0.57)
        widget.toggle_draw_mode(False, create_mode="polygon")
        widget.toggle_brush_polygon_mode()
        pending = Shape(shape_type="polygon")
        direction = 1 if name == "edge" else -1
        pending.points = [anchor + direction * QtCore.QPointF(200, 100),
                          anchor + direction * QtCore.QPointF(150, 80), QtCore.QPointF(anchor)]
        canvas.current = pending
        canvas.line.points = [pending[-1], pending[-1]]
        before = list(pending.points)
        local = (anchor + canvas.offset_to_center()) * canvas.scale
        fixed_global = QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint())) + local
        errors = []
        for delta in (120, 120, 120, -120, -120, -120, -120, -120):
            local = fixed_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
            event = QtGui.QWheelEvent(
                local, fixed_global, QtCore.QPoint(), QtCore.QPoint(0, delta),
                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.ControlModifier,
                QtCore.Qt.ScrollPhase.NoScrollPhase, False)
            canvas.wheelEvent(event)
            QtWidgets.QApplication.processEvents()
            projected = (anchor + canvas.offset_to_center()) * canvas.scale
            projected += QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
            error = max(abs(projected.x() - fixed_global.x()),
                        abs(projected.y() - fixed_global.y()))
            errors.append(error)
            assert error <= 1, (name, delta, error, canvas.scale)
            assert canvas.current is pending and pending.points == before
            # A stationary event after releasing Ctrl must not add a vertex.
            local = fixed_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
            stationary = QtGui.QMouseEvent(
                QtCore.QEvent.Type.MouseMove, local, fixed_global,
                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
                QtCore.Qt.KeyboardModifier.NoModifier)
            canvas.mouseMoveEvent(stationary)
            assert pending.points == before
        # Scrolling beneath a stationary pointer must not create a vertex either.
        local = fixed_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
        scroll = QtGui.QWheelEvent(
            local, fixed_global, QtCore.QPoint(), QtCore.QPoint(0, -120),
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.NoModifier,
            QtCore.Qt.ScrollPhase.NoScrollPhase, False)
        canvas.wheelEvent(scroll)
        local = fixed_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
        stationary = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove, local, fixed_global,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(stationary)
        assert pending.points == before
        # Exercise the actual Space-drag path and its scroll signals.
        canvas._space_pressed = True
        canvas._space_panning = True
        canvas._space_pan_prev_point = QtCore.QPointF(local)
        pan_global = fixed_global + QtCore.QPointF(10, 10)
        pan = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove, local + QtCore.QPointF(10, 10), pan_global,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.LeftButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(pan)
        canvas._space_pressed = canvas._space_panning = False
        canvas._space_pan_suppress_until_release = False
        local = pan_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
        after_pan = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove, local, pan_global,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(after_pan)
        assert pending.points == before
        # Ctrl deliberately pauses following even if the physical pointer moves.
        moved_global = fixed_global + QtCore.QPointF(50, 30)
        local = moved_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
        paused = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove, local, moved_global,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.ControlModifier)
        canvas.mouseMoveEvent(paused)
        assert pending.points == before
        moved_global += QtCore.QPointF(60, 170)
        local = moved_global - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
        resumed = QtGui.QMouseEvent(
            QtCore.QEvent.Type.MouseMove, local, moved_global,
            QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.NoButton,
            QtCore.Qt.KeyboardModifier.NoModifier)
        canvas.mouseMoveEvent(resumed)
        assert len(pending.points) == len(before) + 1
        assert pending.points[:len(before)] == before
        print(f"brush zoom: {name}, max anchor error {max(errors):.3f}px, no extra vertices, resume passed")
        widget.set_fit_window()
        assert canvas._shared_boundary_zoom_padding is None
        canvas.current = None
        canvas._brush_drawing = False


def check_middle_pan(widget):
    """Pan real scrollbars in four directions while protecting the draft."""
    from PyQt6 import QtTest
    from anylabeling.views.labeling.shape import Shape

    for mode in ("brush-fit", "brush-zoom", "polygon"):
        image_path = Path(test_work.name) / f"middle-{mode}.png"
        image = QtGui.QImage(1400, 900, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtCore.Qt.GlobalColor.white)
        assert image.save(str(image_path))
        widget.load_file(str(image_path))
        widget.set_fit_window()
        QtWidgets.QApplication.processEvents()
        old = Shape(label="装修垃圾", shape_type="polygon")
        old.points = [QtCore.QPointF(x, y) for x, y in ((0, 0), (100, 0), (100, 100), (0, 100))]
        old.close()
        widget.load_shapes([old])
        widget.toggle_draw_mode(False, create_mode="polygon")
        if mode.startswith("brush"):
            widget.toggle_brush_polygon_mode()
        canvas = widget.canvas
        pending = Shape(shape_type="polygon")
        pending.points = [QtCore.QPointF(350, 250), QtCore.QPointF(700, 250),
                          QtCore.QPointF(700, 500)]
        canvas.current = pending
        canvas.line.points = [pending[-1], pending[-1]]
        before = list(pending.points)
        history_size = len(canvas.shapes_backups)

        def projected(point):
            return (QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
                    + (point + canvas.offset_to_center()) * canvas.scale)

        def mouse(kind, global_position, button=QtCore.Qt.MouseButton.NoButton,
                  buttons=QtCore.Qt.MouseButton.NoButton):
            local = global_position - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
            return QtGui.QMouseEvent(kind, local, global_position, button, buttons,
                                    QtCore.Qt.KeyboardModifier.NoModifier)

        start = projected(pending[-1])
        if mode == "brush-zoom":
            local = start - QtCore.QPointF(canvas.mapToGlobal(QtCore.QPoint()))
            canvas.wheelEvent(QtGui.QWheelEvent(
                local, start, QtCore.QPoint(), QtCore.QPoint(0, -120),
                QtCore.Qt.MouseButton.NoButton, QtCore.Qt.KeyboardModifier.ControlModifier,
                QtCore.Qt.ScrollPhase.NoScrollPhase, False))
            QtWidgets.QApplication.processEvents()
        start = projected(pending[-1])
        canvas.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress, start,
                                    QtCore.Qt.MouseButton.MiddleButton,
                                    QtCore.Qt.MouseButton.MiddleButton))
        QtWidgets.QApplication.processEvents()
        initial = projected(pending[-1])
        assert max(abs(initial.x() - start.x()), abs(initial.y() - start.y())) <= 1
        for dx, dy in ((90, 0), (90, 70), (-60, 70), (-60, -50)):
            pointer = start + QtCore.QPointF(dx, dy)
            canvas.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove, pointer,
                                        buttons=QtCore.Qt.MouseButton.MiddleButton))
            QtWidgets.QApplication.processEvents()
            actual = projected(pending[-1]) - initial
            assert abs(actual.x() - dx) <= 1 and abs(actual.y() - dy) <= 1, (mode, dx, dy, actual)
            assert canvas.current is pending and pending.points == before
            assert len(canvas.shapes_backups) == history_size
        canvas.mouseReleaseEvent(mouse(QtCore.QEvent.Type.MouseButtonRelease, pointer,
                                      QtCore.Qt.MouseButton.MiddleButton))
        assert canvas._shared_boundary_middle_pan is None
        # Returning the pointer to the boundary after the pan must be harmless.
        endpoint = projected(pending[-1])
        for target in (endpoint + QtCore.QPointF(130, 100), endpoint):
            canvas.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove, target))
            assert pending.points == before
        if mode.startswith("brush"):
            assert canvas._shared_boundary_paused_draft is pending
            canvas.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress, endpoint,
                                        QtCore.Qt.MouseButton.LeftButton,
                                        QtCore.Qt.MouseButton.LeftButton))
            canvas.mouseReleaseEvent(mouse(QtCore.QEvent.Type.MouseButtonRelease, endpoint,
                                          QtCore.Qt.MouseButton.LeftButton))
            assert pending.points == before  # Resume click is not a vertex.
            canvas.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove,
                                        endpoint + QtCore.QPointF(-90, 80)))
        else:
            canvas.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress,
                                        endpoint + QtCore.QPointF(-90, 80),
                                        QtCore.Qt.MouseButton.LeftButton,
                                        QtCore.Qt.MouseButton.LeftButton))
        assert len(pending.points) == len(before) + 1 and pending.points[:3] == before
        # A missing release (outside the window) and loss of focus cannot leave
        # middle-drag active or silently resume following.
        if mode.startswith("brush"):
            endpoint = projected(pending[-1])
            canvas.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress, endpoint,
                                        QtCore.Qt.MouseButton.MiddleButton,
                                        QtCore.Qt.MouseButton.MiddleButton))
            canvas.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove, endpoint))
            assert canvas._shared_boundary_middle_pan is None
            canvas.mousePressEvent(mouse(QtCore.QEvent.Type.MouseButtonPress, endpoint,
                                        QtCore.Qt.MouseButton.MiddleButton,
                                        QtCore.Qt.MouseButton.MiddleButton))
            canvas.focusOutEvent(QtGui.QFocusEvent(QtCore.QEvent.Type.FocusOut))
            assert canvas._shared_boundary_middle_pan is None
            canvas.mouseMoveEvent(mouse(QtCore.QEvent.Type.MouseMove,
                                        endpoint + QtCore.QPointF(100, 100)))
            assert len(pending.points) == 4
        original_popup = widget.label_dialog.pop_up
        widget.label_dialog.pop_up = lambda *a, **k: ("工程渣土", {}, None, "", False, [])
        try:
            QtTest.QTest.keyClick(canvas, QtCore.Qt.Key.Key_Return)
        finally:
            widget.label_dialog.pop_up = original_popup
        assert canvas.current is None and len(canvas.shapes) == 2
        output = image_path.with_suffix(".json")
        assert widget.save_labels(str(output))
        saved = next(s["points"] for s in json.loads(output.read_text(encoding="utf-8"))["shapes"]
                     if s["label"] == "工程渣土")
        assert saved == [[p.x(), p.y()] for p in pending.points]
        widget.undo_shape_edit()
        assert len(canvas.shapes) == 1 and canvas.shapes[0].points == old.points
        print(f"middle pan: {mode}, four directions, safe resume, JSON and Undo passed")


def quick_exec(app):
    # Fail safely if a regression unexpectedly opens an unattended modal dialog.
    watchdog = QtCore.QTimer(app)
    watchdog.setSingleShot(True)
    watchdog.timeout.connect(lambda: app.exit(2))
    watchdog.start(60000)
    def check():
        actions = [
            action
            for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "旧区域优先：自动裁剪新多边形（共边）"
        ]
        refine_actions = [
            action
            for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "共边精修：联动相邻类别"
        ]
        detail_actions = [
            action
            for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "SAM2 细节优先（局部裁剪 + 细轮廓）"
        ]
        straighten_actions = [
            action
            for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "拉直一段边界（点起点和终点）"
        ]
        row_buttons = [
            button
            for window in app.topLevelWidgets()
            for button in window.findChildren(QtWidgets.QPushButton)
            if "从它自身扣除重叠" in button.text()
        ]
        box_actions = [
            action for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "多边形圈选顶点拉直"
        ]
        box_buttons = [
            button for window in app.topLevelWidgets()
            for button in window.findChildren(QtWidgets.QPushButton)
            if button.text() == "多边形圈选顶点拉直"
        ]
        same_buttons = [
            button for window in app.topLevelWidgets()
            for button in window.findChildren(QtWidgets.QPushButton)
            if button.text() == "从当前对象扣除同类重叠"
        ]
        spacing_actions = [
            action for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "画笔多边形点间距…"
        ]
        print("shared boundary menu:", len(actions))
        print("enabled by default:", actions[0].isChecked() if actions else False)
        print("linked refinement menu:", len(refine_actions))
        print("SAM2 detail preset:", len(detail_actions))
        print("straighten boundary tool:", len(straighten_actions))
        print("Shapes row deduction button:", len(row_buttons))
        print("polygon selection action and button:", len(box_actions), len(box_buttons))
        print("same class deduction button:", len(same_buttons))
        if actions:
            check_existing_priority(actions[0].parent())
            check_cancelled_drawing(actions[0].parent())
            check_brush_zoom(actions[0].parent())
            check_middle_pan(actions[0].parent())
        if spacing_actions:
            widget = spacing_actions[0].parent()
            controller = widget._settings_controller
            original_config = copy.deepcopy(widget._config)
            original_save_callback = controller._save_callback
            original_spacing = widget.canvas.brush_point_distance
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
                settings_file = Path(directory) / "settings.json"
                controller._save_callback = lambda config: settings_file.write_text(
                    json.dumps(config, ensure_ascii=False), encoding="utf-8")
                try:
                    spacing_actions[0].trigger()
                    dialog = widget._settings_dialog
                    row = dialog._field_rows["canvas.brush.point_distance"]
                    editor = row.findChild(QtWidgets.QDoubleSpinBox)
                    assert editor.minimum() == 1 and editor.maximum() == 200
                    editor.setValue(5.0)
                    assert widget.canvas.brush_point_distance == original_spacing
                    dialog.shortcuts_save_button.click()
                    assert widget.canvas.brush_point_distance == 5.0
                    saved = json.loads(settings_file.read_text(encoding="utf-8"))
                    assert saved["canvas"]["brush"]["point_distance"] == 5.0
                    print("point spacing setting: navigation, save and runtime update passed")
                finally:
                    dialog.close()
                    widget._config.clear()
                    widget._config.update(original_config)
                    controller.discard_changes()
                    controller._save_callback = original_save_callback
                    widget.canvas.brush_point_distance = original_spacing
        app.quit()
        if not actions or not actions[0].isChecked() or not refine_actions or not detail_actions or not straighten_actions or not row_buttons or not box_actions or not box_buttons or not same_buttons or not spacing_actions:
            raise RuntimeError("shared boundary menu is not active")

    def guarded_check():
        try:
            check()
        except Exception:
            import traceback
            traceback.print_exc()
            app.exit(1)

    QtCore.QTimer.singleShot(1000, guarded_check)
    return original_exec()


QtWidgets.QApplication.exec = quick_exec
try:
    runpy.run_path(str(Path(__file__).with_name("launch.py")), run_name="__main__")
finally:
    test_work.cleanup()
