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


def quick_exec(app):
    def check():
        actions = [
            action
            for window in app.topLevelWidgets()
            for action in window.findChildren(QtGui.QAction)
            if action.text() == "新区域覆盖旧多边形（共边）"
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

    QtCore.QTimer.singleShot(1000, check)
    return original_exec()


QtWidgets.QApplication.exec = quick_exec
try:
    runpy.run_path(str(Path(__file__).with_name("launch.py")), run_name="__main__")
finally:
    test_work.cleanup()
