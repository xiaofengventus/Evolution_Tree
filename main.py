import json
import math
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QBrush, QFont, QFontMetricsF, QKeySequence, QPageSize, QPainter, QPainterPath, QPainterPathStroker, QPdfWriter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QFormLayout,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QRubberBand,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TreeNode:
    """A lightweight editable multi-child evolution-tree node."""

    def __init__(self, name, branch_length=120, branch_color="#7EC8E3", text_color="#111827"):
        self.name = name
        self.branch_length = branch_length
        self.branch_color = branch_color
        self.text_color = text_color
        self.color = branch_color
        self.clade_color = None
        self.children = []
        self.parent = None
        self.hide_children = False

        self.computed_x = 0
        self.computed_y = 0
        self.manual_dx = 0
        self.manual_dy = 0
        self.angle = 0
        self.radius = 0
        self.leaf_span = (0, 0)

    def add_child(self, child_node):
        if child_node is self or self.is_descendant_of(child_node):
            return False
        if child_node.parent is not None and child_node in child_node.parent.children:
            child_node.parent.children.remove(child_node)
        child_node.parent = self
        self.children.append(child_node)
        return True

    def is_descendant_of(self, possible_parent):
        node = self.parent
        while node is not None:
            if node is possible_parent:
                return True
            node = node.parent
        return False

    def is_visible_leaf(self):
        return len(self.children) == 0 or self.hide_children

    def descendants(self):
        nodes = [self]
        for child in self.children:
            nodes.extend(child.descendants())
        return nodes


class NodeLabelItem(QGraphicsTextItem):
    """Editable, selectable, draggable node label."""

    name_changed = pyqtSignal(object, str)
    color_requested = pyqtSignal(object)
    subtree_color_requested = pyqtSignal(object)
    clade_color_requested = pyqtSignal(object)
    clade_clear_requested = pyqtSignal(object)
    hovered = pyqtSignal(object)
    reparent_requested = pyqtSignal(object, object)

    def __init__(self, node, main_window, display_text=None):
        super().__init__(display_text or node.name)
        self.node = node
        self.main_window = main_window
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.editing = False
        self.additive_click = False
        self.setFont(main_window.label_font)
        self.setDefaultTextColor(QColor(node.text_color))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAcceptHoverEvents(True)
        self.setZValue(10)
        self.name_changed.connect(main_window.set_node_name)
        self.color_requested.connect(main_window.change_node_color)
        self.subtree_color_requested.connect(main_window.change_subtree_branch_color)
        self.clade_color_requested.connect(main_window.change_node_clade_color)
        self.clade_clear_requested.connect(main_window.clear_node_clade_color)
        self.hovered.connect(main_window.hover_node)
        self.reparent_requested.connect(main_window.reparent_nodes)

    def mousePressEvent(self, event):
        if self.editing:
            super().mousePressEvent(event)
            return
        self.drag_start = event.scenePos()
        self.last_drag_pos = event.scenePos()
        self.dragging = False
        self.additive_click = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        preserve_existing = (not self.additive_click and self.node in self.main_window.selected_nodes and len(self.main_window.selected_nodes) > 1)
        self.main_window.select_node(self.node, redraw=False, additive=self.additive_click, preserve_existing=preserve_existing)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.editing:
            super().mouseMoveEvent(event)
            return
        if self.drag_start is None:
            event.ignore()
            return
        distance = (event.scenePos() - self.drag_start).manhattanLength()
        if distance > 4:
            self.dragging = True
            self.main_window.move_drag_preview(self.node, event.scenePos() - self.last_drag_pos)
            self.main_window.update_drop_hint(event.scenePos(), self.node)
            self.last_drag_pos = event.scenePos()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self.editing:
            super().mouseReleaseEvent(event)
            return
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.dragging:
            target = self.main_window.node_at(event.scenePos(), exclude=self.main_window.preview_nodes_for_drag(self.node))
            self.main_window.finish_node_drag(self.node, target)
        elif not self.additive_click:
            self.main_window.select_node(self.node)
        else:
            self.main_window.redraw_tree()
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.additive_click = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.main_window.edit_node_name(self.node)
        event.accept()

    def focusOutEvent(self, event):
        if self.editing:
            self.editing = False
            self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
            self.name_changed.emit(self.node, self.toPlainText().strip())
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if self.editing and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.clearFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def hoverEnterEvent(self, event):
        self.hovered.emit(self.node)
        self.setDefaultTextColor(QColor("#111827"))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setDefaultTextColor(QColor(self.node.text_color))
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("直接编辑名称")
        color_action = menu.addAction("修改分支线颜色")
        text_color_action = menu.addAction("修改文本颜色")
        subtree_color_action = menu.addAction("统一子分支颜色")
        clade_action = menu.addAction("设置单系群背景色")
        clear_clade_action = menu.addAction("清除单系群背景色")
        delete_action = menu.addAction("删除节点")
        action = menu.exec(event.screenPos())
        if action is rename_action:
            self.main_window.edit_node_name(self.node)
        elif action is color_action:
            self.color_requested.emit(self.node)
        elif action is text_color_action:
            self.main_window.change_node_text_color(self.node)
        elif action is subtree_color_action:
            self.subtree_color_requested.emit(self.node)
        elif action is clade_action:
            self.clade_color_requested.emit(self.node)
        elif action is clear_clade_action:
            self.clade_clear_requested.emit(self.node)
        elif action is delete_action:
            self.main_window.delete_nodes(self.node)
        event.accept()


class NodeHandleItem(QGraphicsEllipseItem):
    """Small selectable node handle, useful for blank or hidden labels."""

    def __init__(self, node, main_window, x, y):
        super().__init__(-5, -5, 10, 10)
        self.node = node
        self.main_window = main_window
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.additive_click = False
        self.setPos(x, y)
        self.setBrush(QBrush(QColor("#FFFFFF")))
        self.setPen(QPen(QColor(node.branch_color), 2))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAcceptHoverEvents(True)
        self.setZValue(12)

    def mousePressEvent(self, event):
        self.drag_start = event.scenePos()
        self.last_drag_pos = event.scenePos()
        self.dragging = False
        self.additive_click = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        preserve_existing = (not self.additive_click and self.node in self.main_window.selected_nodes and len(self.main_window.selected_nodes) > 1)
        self.main_window.select_node(self.node, redraw=False, additive=self.additive_click, preserve_existing=preserve_existing)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            event.ignore()
            return
        distance = (event.scenePos() - self.drag_start).manhattanLength()
        if distance > 4:
            self.dragging = True
            self.main_window.move_drag_preview(self.node, event.scenePos() - self.last_drag_pos)
            self.main_window.update_drop_hint(event.scenePos(), self.node)
            self.last_drag_pos = event.scenePos()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.dragging:
            target = self.main_window.node_at(event.scenePos(), exclude=self.main_window.preview_nodes_for_drag(self.node))
            self.main_window.finish_node_drag(self.node, target)
        elif not self.additive_click:
            self.main_window.select_node(self.node)
        else:
            self.main_window.redraw_tree()
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.additive_click = False
        event.accept()

    def hoverEnterEvent(self, event):
        self.main_window.hover_node(self.node)
        self.setBrush(QBrush(QColor("#D6EAF8")))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor("#FFFFFF")))
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("编辑节点名称")
        color_action = menu.addAction("修改分支线颜色")
        text_color_action = menu.addAction("修改文本颜色")
        subtree_color_action = menu.addAction("统一子分支颜色")
        clade_action = menu.addAction("设置单系群背景色")
        clear_clade_action = menu.addAction("清除单系群背景色")
        delete_action = menu.addAction("删除节点")
        action = menu.exec(event.screenPos())
        if action is rename_action:
            self.main_window.edit_node_name(self.node)
        elif action is color_action:
            self.main_window.change_node_color(self.node)
        elif action is text_color_action:
            self.main_window.change_node_text_color(self.node)
        elif action is subtree_color_action:
            self.main_window.change_subtree_branch_color(self.node)
        elif action is clade_action:
            self.main_window.change_node_clade_color(self.node)
        elif action is clear_clade_action:
            self.main_window.clear_node_clade_color(self.node)
        elif action is delete_action:
            self.main_window.delete_nodes(self.node)
        event.accept()


class BranchLineItem(QGraphicsLineItem):
    """Interactive branch segment, so branches can be selected directly."""

    def __init__(self, node, main_window, x1, y1, x2, y2, pen):
        super().__init__(x1, y1, x2, y2)
        self.node = node
        self.main_window = main_window
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.additive_click = False
        self.setPen(pen)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(1)

    def shape(self):
        path = QPainterPath()
        line = self.line()
        path.moveTo(line.p1())
        path.lineTo(line.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(18)
        return stroker.createStroke(path)

    def mousePressEvent(self, event):
        self.drag_start = event.scenePos()
        self.last_drag_pos = event.scenePos()
        self.dragging = False
        self.additive_click = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        preserve_existing = (not self.additive_click and self.node in self.main_window.selected_nodes and len(self.main_window.selected_nodes) > 1)
        self.main_window.select_node(self.node, redraw=False, additive=self.additive_click, preserve_existing=preserve_existing)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            event.ignore()
            return
        if (event.scenePos() - self.drag_start).manhattanLength() > 4:
            self.dragging = True
            self.main_window.move_drag_preview(self.node, event.scenePos() - self.last_drag_pos)
            self.main_window.update_drop_hint(event.scenePos(), self.node)
            self.last_drag_pos = event.scenePos()
            event.accept()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.dragging:
            target = self.main_window.node_at(event.scenePos(), exclude=self.main_window.preview_nodes_for_drag(self.node))
            self.main_window.finish_node_drag(self.node, target)
        elif not self.additive_click:
            self.main_window.select_node(self.node)
        else:
            self.main_window.redraw_tree()
        self.drag_start = None
        self.last_drag_pos = None
        self.dragging = False
        self.additive_click = False
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.main_window.edit_node_name(self.node)
        event.accept()

    def hoverEnterEvent(self, event):
        self.main_window.hover_node(self.node)
        pen = QPen(self.pen())
        pen.setWidth(max(pen.width(), 5))
        self.setPen(pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self.main_window.node_pen(self.node))
        super().hoverLeaveEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        rename_action = menu.addAction("编辑节点名称")
        color_action = menu.addAction("修改分支线颜色")
        text_color_action = menu.addAction("修改文本颜色")
        subtree_color_action = menu.addAction("统一子分支颜色")
        clade_action = menu.addAction("设置单系群背景色")
        clear_clade_action = menu.addAction("清除单系群背景色")
        delete_action = menu.addAction("删除节点")
        action = menu.exec(event.screenPos())
        if action is rename_action:
            self.main_window.edit_node_name(self.node)
        elif action is color_action:
            self.main_window.change_node_color(self.node)
        elif action is text_color_action:
            self.main_window.change_node_text_color(self.node)
        elif action is subtree_color_action:
            self.main_window.change_subtree_branch_color(self.node)
        elif action is clade_action:
            self.main_window.change_node_clade_color(self.node)
        elif action is clear_clade_action:
            self.main_window.clear_node_clade_color(self.node)
        elif action is delete_action:
            self.main_window.delete_nodes(self.node)
        event.accept()


class TreeView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.main_window = parent
        self.rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.rubber_origin = QPoint()
        self.is_rubber_selecting = False
        self.rubber_additive = False

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        additive = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        if event.button() == Qt.MouseButton.LeftButton and not item:
            self.is_rubber_selecting = True
            self.rubber_additive = additive
            self.rubber_origin = event.position().toPoint()
            self.rubber_band.setGeometry(QRect(self.rubber_origin, self.rubber_origin))
            self.rubber_band.show()
            event.accept()
            return

        if not item:
            self.main_window.select_node(None)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_rubber_selecting:
            rect = QRect(self.rubber_origin, event.position().toPoint()).normalized()
            self.rubber_band.setGeometry(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_rubber_selecting:
            self.rubber_band.hide()
            view_rect = QRect(self.rubber_origin, event.position().toPoint()).normalized()
            if view_rect.width() < 4 and view_rect.height() < 4:
                if not self.rubber_additive:
                    self.main_window.select_node(None)
            else:
                scene_rect = self.mapToScene(view_rect).boundingRect()
                self.main_window.select_nodes_in_scene_rect(scene_rect, additive=self.rubber_additive)
            self.is_rubber_selecting = False
            self.rubber_additive = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self.main_window.undo()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.main_window.delete_nodes()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.main_window.copy_selected_subtrees()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.main_window.paste_from_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)


class DIYEvolutionTree(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DIY 进化树可视化设计器 (iTOL 自由交互版)")
        self.resize(1320, 820)

        self.root = TreeNode("起始节点", 0)

        self.selected_node = None
        self.selected_nodes = set()
        self.align_right = False
        self.hide_internal_names = False
        self.layout_mode = "rectangular"
        self.node_spacing = 42
        self.branch_gap = 14
        self.auto_branch_length = True
        self.label_wrap_lines = 2
        self.label_position_mode = "above"
        self.label_font = QFont("Microsoft YaHei", 10)
        self.node_items = {}
        self.node_graphics = {}
        self.undo_stack = []
        self.is_restoring = False
        self.drag_roots = []
        self.drag_delta = QPointF(0, 0)
        self.drop_hint_item = None
        self.active_name_editor = None
        self.leaf_counter = 0
        self.max_tree_x = 0
        self.scene_center = QPointF(0, 0)
        self.radial_max_radius = 360

        self.init_ui()
        self.redraw_tree()

    def init_ui(self):
        main_widget = QWidget()
        layout = QHBoxLayout(main_widget)

        self.scene = QGraphicsScene()
        self.view = TreeView(self.scene, self)
        layout.addWidget(self.view, stretch=5)

        self.control_panel = QWidget()
        self.control_panel.setMinimumWidth(330)
        panel_layout = QVBoxLayout(self.control_panel)
        self.build_control_panel(panel_layout)
        layout.addWidget(self.control_panel, stretch=0)

        self.setCentralWidget(main_widget)

    def build_control_panel(self, layout):
        global_group = QGroupBox("全局布局与显示")
        global_form = QFormLayout(global_group)

        self.cmb_layout = QComboBox()
        self.cmb_layout.addItem("矩形树 Rectangular", "rectangular")
        self.cmb_layout.addItem("环形/圆形树 Circular", "circular")
        self.cmb_layout.addItem("无根/放射树 Radial", "radial")
        self.cmb_layout.currentIndexChanged.connect(self.change_layout)
        global_form.addRow("布局", self.cmb_layout)

        self.cb_align = QCheckBox("物种名称对齐到最右侧")
        self.cb_align.stateChanged.connect(self.toggle_align_right)
        global_form.addRow(self.cb_align)

        self.cb_hide_internal_names = QCheckBox("隐藏中间非叶节点名称")
        self.cb_hide_internal_names.stateChanged.connect(self.toggle_internal_names)
        global_form.addRow(self.cb_hide_internal_names)

        self.slider_spacing = QSlider(Qt.Orientation.Horizontal)
        self.slider_spacing.setRange(22, 96)
        self.slider_spacing.setValue(self.node_spacing)
        self.slider_spacing.valueChanged.connect(self.change_node_spacing)
        global_form.addRow("节点间隔高度", self.slider_spacing)

        self.cb_auto_branch_length = QCheckBox("分支长度自适应名字长度")
        self.cb_auto_branch_length.setChecked(self.auto_branch_length)
        self.cb_auto_branch_length.stateChanged.connect(self.toggle_auto_branch_length)
        global_form.addRow(self.cb_auto_branch_length)

        self.cmb_wrap_lines = QComboBox()
        self.cmb_wrap_lines.addItem("1 行", 1)
        self.cmb_wrap_lines.addItem("2 行", 2)
        self.cmb_wrap_lines.addItem("3 行", 3)
        self.cmb_wrap_lines.setCurrentIndex(1)
        self.cmb_wrap_lines.currentIndexChanged.connect(self.change_label_wrap_lines)
        global_form.addRow("标签换行", self.cmb_wrap_lines)

        self.cmb_label_position = QComboBox()
        self.cmb_label_position.addItem("全部在线条上方", "above")
        self.cmb_label_position.addItem("线条上下分布", "mixed")
        self.cmb_label_position.currentIndexChanged.connect(self.change_label_position_mode)
        global_form.addRow("标签位置", self.cmb_label_position)

        self.btn_export_pdf = QPushButton("导出 PDF")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        global_form.addRow(self.btn_export_pdf)

        file_row = QWidget()
        file_buttons = QHBoxLayout(file_row)
        file_buttons.setContentsMargins(0, 0, 0, 0)
        self.btn_save_tree = QPushButton("保存")
        self.btn_save_tree.clicked.connect(self.save_tree_file)
        file_buttons.addWidget(self.btn_save_tree)
        self.btn_open_tree = QPushButton("打开")
        self.btn_open_tree.clicked.connect(self.open_tree_file)
        file_buttons.addWidget(self.btn_open_tree)
        global_form.addRow(file_row)

        self.btn_reset_single = QPushButton("从 0 开始：仅保留一个节点")
        self.btn_reset_single.clicked.connect(self.reset_to_single_node)
        global_form.addRow(self.btn_reset_single)
        layout.addWidget(global_group)

        self.node_group = QGroupBox("选中分支 DIY 修饰")
        node_form = QFormLayout(self.node_group)

        self.lbl_selected = QLabel("未选中任何节点")
        self.lbl_selected.setStyleSheet("font-weight: bold; color: #566573;")
        self.lbl_selected.setWordWrap(True)
        node_form.addRow(self.lbl_selected)

        self.edit_name = QLineEdit()
        self.edit_name.editingFinished.connect(self.rename_selected_node)
        node_form.addRow("节点名", self.edit_name)

        self.btn_add = QPushButton("在当前分支下添加新物种")
        self.btn_add.clicked.connect(self.diy_add_node)
        node_form.addRow(self.btn_add)

        self.btn_add_blank = QPushButton("添加空白无名字节点")
        self.btn_add_blank.clicked.connect(self.diy_add_blank_node)
        node_form.addRow(self.btn_add_blank)

        self.btn_delete = QPushButton("删除选中节点")
        self.btn_delete.clicked.connect(lambda _checked=False: self.delete_nodes())
        node_form.addRow(self.btn_delete)

        self.btn_color = QPushButton("改变本节点分支线颜色")
        self.btn_color.clicked.connect(self.diy_change_color)
        node_form.addRow(self.btn_color)

        self.btn_text_color = QPushButton("改变本节点文本颜色")
        self.btn_text_color.clicked.connect(self.diy_change_text_color)
        node_form.addRow(self.btn_text_color)

        self.btn_subtree_color = QPushButton("统一子节点分支颜色")
        self.btn_subtree_color.clicked.connect(self.diy_change_subtree_color)
        node_form.addRow(self.btn_subtree_color)

        self.btn_clade_color = QPushButton("为整个单系群添加背景色")
        self.btn_clade_color.clicked.connect(self.diy_change_clade_color)
        node_form.addRow(self.btn_clade_color)

        self.btn_clear_clade = QPushButton("清除单系群背景色")
        self.btn_clear_clade.clicked.connect(self.diy_clear_clade_color)
        node_form.addRow(self.btn_clear_clade)

        self.slider_length = QSlider(Qt.Orientation.Horizontal)
        self.slider_length.setRange(20, 500)
        self.slider_length.valueChanged.connect(self.diy_change_length)
        node_form.addRow("树枝长度 / 演化跨度", self.slider_length)

        self.cb_hide_children = QCheckBox("折叠后代分支为科学三角形")
        self.cb_hide_children.stateChanged.connect(self.diy_toggle_hide_children)
        node_form.addRow(self.cb_hide_children)

        layout.addWidget(self.node_group)
        self.node_group.setEnabled(False)

        paste_group = QGroupBox("粘贴名单建树")
        paste_layout = QVBoxLayout(paste_group)
        self.txt_names = QTextEdit()
        self.txt_names.setPlaceholderText(
            "每行一个名称；会作为当前选中节点的子节点。\n"
            "也支持缩进层级，例如：\n"
            "脊椎动物\n"
            "  鱼类\n"
            "  四足动物"
        )
        self.txt_names.setMinimumHeight(135)
        paste_layout.addWidget(self.txt_names)

        paste_buttons = QHBoxLayout()
        self.btn_paste_selected = QPushButton("加到选中节点")
        self.btn_paste_selected.clicked.connect(self.add_names_to_selected)
        paste_buttons.addWidget(self.btn_paste_selected)
        self.btn_replace_root = QPushButton("重建整棵树")
        self.btn_replace_root.clicked.connect(self.rebuild_tree_from_paste)
        paste_buttons.addWidget(self.btn_replace_root)
        paste_layout.addLayout(paste_buttons)
        layout.addWidget(paste_group)

        hint = QLabel("拖拽任意节点名称或小圆点到另一个节点上，可把它连接为新的父子关系。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #6C7A89;")
        layout.addWidget(hint)
        layout.addStretch()

    def visible_children(self, node):
        return [] if node.hide_children else node.children

    def all_nodes(self, node=None):
        node = self.root if node is None else node
        nodes = [node]
        for child in node.children:
            nodes.extend(self.all_nodes(child))
        return nodes

    def visible_leaves(self, node):
        if node.is_visible_leaf():
            return [node]
        leaves = []
        for child in node.children:
            leaves.extend(self.visible_leaves(child))
        return leaves

    def descendant_leaf_count(self, node):
        if len(node.children) == 0:
            return 1
        return sum(self.descendant_leaf_count(child) for child in node.children)

    def descendant_max_span(self, node):
        if len(node.children) == 0:
            return node.branch_length
        return node.branch_length + max(self.descendant_max_span(child) for child in node.children)

    def redraw_tree(self):
        self.close_active_name_editor()
        self.scene.clear()
        self.node_items = {}
        self.node_graphics = {}
        self.max_tree_x = 0
        self.get_max_depth(self.root, 50)

        if self.layout_mode == "rectangular":
            self.layout_rectangular()
            self.apply_manual_offsets(self.root)
            self.draw_rectangular_backgrounds(self.root)
            self.draw_rectangular_node(self.root, 50)
        else:
            self.layout_radial()
            self.apply_manual_offsets(self.root)
            self.draw_radial_backgrounds(self.root)
            self.draw_radial_node(self.root)

        rect = self.scene.itemsBoundingRect().adjusted(-70, -70, 90, 70)
        self.scene.setSceneRect(rect)

    def register_node_graphic(self, node, item):
        self.node_graphics.setdefault(node, []).append(item)
        return item

    def sanitized_root_name(self):
        raw_name = (self.root.name or "tree").strip()
        safe_name = re.sub(r'[<>:"/\\\\|?*]+', "_", raw_name)
        safe_name = safe_name.strip(" .")
        return safe_name or "tree"

    def default_json_filename(self):
        return f"{self.sanitized_root_name()}.json"

    def default_pdf_filename(self):
        return f"{self.sanitized_root_name()}.pdf"

    def autosave_path(self):
        script_dir = Path(__file__).resolve().parent
        return script_dir / f"{self.sanitized_root_name()}_autosave.json"

    def save_state_to_path(self, path):
        data = self.current_state()
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)

    def autosave_json(self):
        path = self.autosave_path()
        self.save_state_to_path(path)
        return path

    def wrap_text_lines(self, text):
        text = (text or "").strip()
        if not text:
            return [""]
        max_lines = max(1, self.label_wrap_lines)
        if max_lines == 1:
            return [text]
        if re.fullmatch(r"[A-Za-z0-9_\-./]+", text):
            return [text]

        if " " in text:
            words = text.split()
            target = max(4, math.ceil(sum(len(word) for word in words) / max_lines))
            lines = []
            current = []
            current_len = 0
            for word in words:
                projected = current_len + len(word) + (1 if current else 0)
                remaining_words = len(words) - (len(lines) + len(current))
                if current and projected > target and len(lines) < max_lines - 1:
                    lines.append(" ".join(current))
                    current = [word]
                    current_len = len(word)
                else:
                    current.append(word)
                    current_len = projected
            if current:
                lines.append(" ".join(current))
        else:
            chunk = max(1, math.ceil(len(text) / max_lines))
            lines = [text[index:index + chunk] for index in range(0, len(text), chunk)]

        if len(lines) > max_lines:
            head = lines[: max_lines - 1]
            tail = " ".join(lines[max_lines - 1:]) if " " in text else "".join(lines[max_lines - 1:])
            lines = head + [tail]
        while len(lines) < max_lines and len(lines) > 1:
            lines.append("")
        return [line for line in lines if line]

    def node_label_lines(self, node):
        return self.wrap_text_lines(node.name)

    def node_label_text(self, node):
        return "\n".join(self.node_label_lines(node))

    def node_label_width(self, node):
        metrics = QFontMetricsF(self.label_font)
        return max(metrics.horizontalAdvance(line) for line in self.node_label_lines(node))

    def effective_branch_length(self, node):
        if not self.auto_branch_length or self.layout_mode != "rectangular":
            return node.branch_length
        padding = 18
        return max(node.branch_length, int(self.node_label_width(node) + padding))

    def current_state(self):
        return {
            "version": 1,
            "layout_mode": self.layout_mode,
            "align_right": self.align_right,
            "hide_internal_names": self.hide_internal_names,
            "node_spacing": self.node_spacing,
            "auto_branch_length": self.auto_branch_length,
            "label_wrap_lines": self.label_wrap_lines,
            "label_position_mode": self.label_position_mode,
            "root": self.serialize_node(self.root),
        }

    def apply_state(self, data):
        self.root = self.deserialize_node(data["root"])
        self.layout_mode = data.get("layout_mode", "rectangular")
        self.align_right = bool(data.get("align_right", False))
        self.hide_internal_names = bool(data.get("hide_internal_names", False))
        self.node_spacing = int(data.get("node_spacing", 42))
        self.auto_branch_length = bool(data.get("auto_branch_length", True))
        self.label_wrap_lines = int(data.get("label_wrap_lines", 2))
        self.label_position_mode = data.get("label_position_mode", "above")

        index = self.cmb_layout.findData(self.layout_mode)
        if index >= 0:
            self.cmb_layout.blockSignals(True)
            self.cmb_layout.setCurrentIndex(index)
            self.cmb_layout.blockSignals(False)
        self.cb_align.blockSignals(True)
        self.cb_align.setChecked(self.align_right)
        self.cb_align.blockSignals(False)
        self.cb_hide_internal_names.blockSignals(True)
        self.cb_hide_internal_names.setChecked(self.hide_internal_names)
        self.cb_hide_internal_names.blockSignals(False)
        self.slider_spacing.blockSignals(True)
        self.slider_spacing.setValue(max(22, min(96, self.node_spacing)))
        self.slider_spacing.blockSignals(False)
        self.cb_auto_branch_length.blockSignals(True)
        self.cb_auto_branch_length.setChecked(self.auto_branch_length)
        self.cb_auto_branch_length.blockSignals(False)
        wrap_index = max(0, min(2, self.label_wrap_lines - 1))
        self.cmb_wrap_lines.blockSignals(True)
        self.cmb_wrap_lines.setCurrentIndex(wrap_index)
        self.cmb_wrap_lines.blockSignals(False)
        position_index = self.cmb_label_position.findData(self.label_position_mode)
        if position_index >= 0:
            self.cmb_label_position.blockSignals(True)
            self.cmb_label_position.setCurrentIndex(position_index)
            self.cmb_label_position.blockSignals(False)

        self.selected_node = self.root
        self.selected_nodes = {self.root}
        self.select_node(self.root)

    def push_undo(self):
        if self.is_restoring:
            return
        self.undo_stack.append(json.loads(json.dumps(self.current_state(), ensure_ascii=False)))
        if len(self.undo_stack) > 80:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            return
        state = self.undo_stack.pop()
        self.is_restoring = True
        try:
            self.apply_state(state)
        finally:
            self.is_restoring = False

    def move_drag_preview(self, dragged_node, delta):
        if not self.drag_roots:
            self.drag_roots = self.drag_roots_for(dragged_node)
            self.drag_delta = QPointF(0, 0)
        self.drag_delta = self.drag_delta + delta
        nodes = self.preview_nodes_for_drag(dragged_node)
        seen = set()
        for node in nodes:
            for item in self.node_graphics.get(node, []):
                if id(item) not in seen:
                    item.moveBy(delta.x(), delta.y())
                    seen.add(id(item))

    def drag_roots_for(self, dragged_node):
        roots = list(self.selected_nodes) if dragged_node in self.selected_nodes else [dragged_node]
        result = []
        for node in roots:
            if not any(node.is_descendant_of(other) for other in roots if other is not node):
                result.append(node)
        return result

    def preview_nodes_for_drag(self, dragged_node):
        roots = self.drag_roots or self.drag_roots_for(dragged_node)
        nodes = []
        for root in roots:
            for node in root.descendants():
                if node not in nodes:
                    nodes.append(node)
        return nodes

    def clear_drop_hint(self):
        if self.drop_hint_item is not None:
            self.scene.removeItem(self.drop_hint_item)
            self.drop_hint_item = None

    def update_drop_hint(self, scene_pos, dragged_node):
        self.clear_drop_hint()
        target = self.node_at(scene_pos, exclude=self.preview_nodes_for_drag(dragged_node))
        if target is None or not self.can_accept_drop(dragged_node, target):
            return
        pen = QPen(QColor("#4A90E2"), 2)
        pen.setStyle(Qt.PenStyle.DashLine)
        self.drop_hint_item = self.scene.addEllipse(
            target.computed_x - 16,
            target.computed_y - 16,
            32,
            32,
            pen,
            QBrush(Qt.BrushStyle.NoBrush),
        )
        self.drop_hint_item.setZValue(30)

    def can_accept_drop(self, dragged_node, new_parent):
        moving_nodes = self.drag_roots or self.drag_roots_for(dragged_node)
        if new_parent is None or new_parent in moving_nodes:
            return False
        return not any(new_parent.is_descendant_of(node) for node in moving_nodes)

    def finish_node_drag(self, dragged_node, new_parent):
        self.clear_drop_hint()
        roots = sorted(self.drag_roots or self.drag_roots_for(dragged_node), key=lambda node: node.computed_y)
        delta = QPointF(self.drag_delta.x(), self.drag_delta.y())
        accepts_drop = self.can_accept_drop(dragged_node, new_parent)
        self.drag_roots = []
        self.drag_delta = QPointF(0, 0)

        if not roots:
            self.redraw_tree()
            return

        self.push_undo()

        if accepts_drop:
            for node in roots:
                if node is not self.root:
                    new_parent.add_child(node)
                    self.reset_subtree_manual_offsets(node)
            new_parent.hide_children = False
        else:
            for root in roots:
                for node in root.descendants():
                    node.manual_dx += delta.x()
                    node.manual_dy += delta.y()

        self.selected_nodes = set(roots)
        self.selected_node = dragged_node if dragged_node in self.selected_nodes else roots[0]
        self.redraw_tree()

    def reset_subtree_manual_offsets(self, node):
        for item in node.descendants():
            item.manual_dx = 0
            item.manual_dy = 0

    def get_max_depth(self, node, current_x):
        next_x = current_x + self.effective_branch_length(node)
        self.max_tree_x = max(self.max_tree_x, next_x)
        if not node.hide_children:
            for child in node.children:
                self.get_max_depth(child, next_x + self.branch_gap)

    def layout_rectangular(self):
        self.leaf_counter = 0
        self.layout_rectangular_node(self.root, 50)

    def layout_rectangular_node(self, node, parent_x):
        node.computed_x = parent_x + self.effective_branch_length(node)
        if node.is_visible_leaf():
            self.leaf_counter += 1
            node.computed_y = self.leaf_counter * self.node_spacing
            node.leaf_span = (node.computed_y, node.computed_y)
            return

        for child in node.children:
            self.layout_rectangular_node(child, node.computed_x + self.branch_gap)
        ys = [child.computed_y for child in node.children]
        node.computed_y = sum(ys) / len(ys)
        node.leaf_span = (min(child.leaf_span[0] for child in node.children), max(child.leaf_span[1] for child in node.children))

    def apply_manual_offsets(self, node):
        node.computed_x += node.manual_dx
        node.computed_y += node.manual_dy
        if self.layout_mode == "rectangular" and node.parent is not None:
            min_x = node.parent.computed_x + max(24, self.branch_gap)
            if node.computed_x < min_x:
                node.computed_x = min_x
        if not node.hide_children:
            for child in node.children:
                self.apply_manual_offsets(child)

    def layout_radial(self):
        leaves = self.visible_leaves(self.root)
        if not leaves:
            return
        angle_margin = math.radians(18 if self.layout_mode == "radial" else 0)
        total_angle = math.tau - angle_margin * 2
        if len(leaves) == 1:
            leaves[0].angle = 0
        else:
            for index, leaf in enumerate(leaves):
                leaf.angle = angle_margin + total_angle * index / len(leaves)

        max_depth = max(1, self.max_path_length(self.root, 0))
        self.radial_max_radius = max(280, min(560, max_depth + 90))
        self.scene_center = QPointF(0, 0)
        self.layout_radial_node(self.root, 0, max_depth)

    def max_path_length(self, node, current):
        current += node.branch_length
        if node.is_visible_leaf():
            return current
        return max(self.max_path_length(child, current) for child in node.children)

    def layout_radial_node(self, node, current_length, max_depth):
        current_length += node.branch_length
        node.radius = 0 if node is self.root else (current_length / max_depth) * self.radial_max_radius

        if node.is_visible_leaf():
            pass
        else:
            for child in node.children:
                self.layout_radial_node(child, current_length, max_depth)
            node.angle = self.mean_angle([child.angle for child in node.children])

        point = self.polar_to_point(node.angle, node.radius)
        node.computed_x = point.x()
        node.computed_y = point.y()

    def mean_angle(self, angles):
        x = sum(math.cos(angle) for angle in angles)
        y = sum(math.sin(angle) for angle in angles)
        return math.atan2(y, x)

    def polar_to_point(self, angle, radius):
        return QPointF(
            self.scene_center.x() + math.cos(angle) * radius,
            self.scene_center.y() + math.sin(angle) * radius,
        )

    def angle_between(self, start, end):
        while end < start:
            end += math.tau
        return start, end

    def draw_rectangular_backgrounds(self, node):
        if node.clade_color:
            self.draw_rectangular_clade_background(node)
        if not node.hide_children:
            for child in node.children:
                self.draw_rectangular_backgrounds(child)

    def draw_rectangular_clade_background(self, node):
        leaves = self.visible_leaves(node)
        if not leaves:
            return
        y_min = min(leaf.computed_y for leaf in leaves) - 24
        y_max = max(leaf.computed_y for leaf in leaves) + 24
        x_min = node.computed_x - 8
        x_max = max(leaf.computed_x for leaf in leaves) + 120
        color = QColor(node.clade_color)
        color.setAlpha(54)
        item = self.scene.addRect(QRectF(x_min, y_min, x_max - x_min, y_max - y_min), QPen(Qt.PenStyle.NoPen), QBrush(color))
        item.setZValue(-10)

    def draw_radial_backgrounds(self, node):
        if node.clade_color:
            self.draw_radial_clade_background(node)
        if not node.hide_children:
            for child in node.children:
                self.draw_radial_backgrounds(child)

    def draw_radial_clade_background(self, node):
        leaves = self.visible_leaves(node)
        if not leaves:
            return
        angles = sorted(leaf.angle % math.tau for leaf in leaves)
        start = angles[0] - math.radians(4)
        end = angles[-1] + math.radians(4)
        if len(angles) > 1 and end - start > math.pi:
            gaps = []
            circular_angles = angles + [angles[0] + math.tau]
            for index in range(len(angles)):
                gaps.append((circular_angles[index + 1] - circular_angles[index], index))
            _, gap_index = max(gaps)
            start = circular_angles[gap_index + 1] - math.radians(4)
            end = circular_angles[gap_index] + math.tau + math.radians(4)
        start, end = self.angle_between(start, end)

        inner = max(0, node.radius - 18)
        outer = max(120, max(leaf.radius for leaf in leaves) + 72)
        path = QPainterPath()
        first_outer = self.polar_to_point(start, outer)
        path.moveTo(first_outer)
        steps = max(8, int((end - start) / math.radians(4)))
        for step in range(1, steps + 1):
            angle = start + (end - start) * step / steps
            path.lineTo(self.polar_to_point(angle, outer))
        for step in range(steps, -1, -1):
            angle = start + (end - start) * step / steps
            path.lineTo(self.polar_to_point(angle, inner))
        path.closeSubpath()

        color = QColor(node.clade_color)
        color.setAlpha(58)
        item = self.scene.addPath(path, QPen(Qt.PenStyle.NoPen), QBrush(color))
        item.setZValue(-10)

    def draw_rectangular_node(self, node, parent_x):
        current_x = node.computed_x
        current_y = node.computed_y
        true_x = current_x

        if self.align_right and node.is_visible_leaf():
            current_x = self.max_tree_x + 40

        pen = self.node_pen(node)
        branch_item = self.add_branch_line(node, parent_x, current_y, true_x, current_y, pen)

        if self.align_right and node.is_visible_leaf() and current_x > true_x:
            dashed = QPen(QColor("#AAB2BD"), 1)
            dashed.setStyle(Qt.PenStyle.DashLine)
            guide = self.scene.addLine(true_x, current_y, current_x, current_y, dashed)
            guide.setZValue(0)

        if node.hide_children and len(node.children) > 0:
            self.draw_collapsed_triangle_rect(node, true_x, current_y)
        elif len(node.children) > 0:
            child_y_min = min(child.computed_y for child in node.children)
            child_y_max = max(child.computed_y for child in node.children)
            split_x = true_x + self.branch_gap
            self.add_branch_line(node, true_x, current_y, split_x, current_y, QPen(QColor(node.branch_color), 2))
            trunk = self.add_branch_line(node, split_x, child_y_min, split_x, child_y_max, QPen(QColor(node.branch_color), 2))
            for child in node.children:
                self.draw_rectangular_node(child, split_x)

        self.add_node_handle(node, true_x, current_y)
        if self.should_draw_label(node):
            if node.is_visible_leaf():
                label = self.add_node_label(node, current_x + 8, current_y - 16)
                self.position_leaf_label(label, current_x, current_y)
            else:
                label = self.add_node_label(node, parent_x + 6, current_y - 24)
                self.position_rectangular_label(label, parent_x, true_x, current_y)

    def draw_radial_node(self, node):
        if node.parent is not None:
            parent_point = QPointF(node.parent.computed_x, node.parent.computed_y)
            node_point = QPointF(node.computed_x, node.computed_y)
            branch = self.add_branch_line(node, parent_point.x(), parent_point.y(), node_point.x(), node_point.y(), self.node_pen(node))

        if node.hide_children and len(node.children) > 0:
            self.draw_collapsed_triangle_radial(node)
        elif len(node.children) > 0:
            for child in node.children:
                self.draw_radial_node(child)

        self.add_node_handle(node, node.computed_x, node.computed_y)
        if self.should_draw_label(node):
            label_radius = node.radius + 10
            if not node.is_visible_leaf():
                label_radius = max(18, node.radius - 24)
            label_point = self.polar_to_point(node.angle, label_radius)
            label = self.add_node_label(node, label_point.x(), label_point.y() - 12)
            if math.cos(node.angle) < 0:
                label.setPos(label_point.x() - label.boundingRect().width() - 8, label_point.y() - 12)

    def draw_collapsed_triangle_rect(self, node, x, y):
        species_count = max(1, self.descendant_leaf_count(node))
        fastest_span = max(40, min(260, self.descendant_max_span(node) * 0.45))
        half_height = max(18, min(90, 10 + species_count * 6))
        triangle = QPolygonF([
            QPointF(x, y),
            QPointF(x + fastest_span, y - half_height),
            QPointF(x + fastest_span, y + half_height),
        ])
        color = QColor(node.branch_color)
        color.setAlpha(95)
        item = self.scene.addPolygon(triangle, QPen(QColor(node.branch_color), 1.5), QBrush(color))
        item.setZValue(2)
        self.register_node_graphic(node, item)

    def draw_collapsed_triangle_radial(self, node):
        species_count = max(1, self.descendant_leaf_count(node))
        span = max(34, min(130, self.descendant_max_span(node) * 0.22))
        width_angle = math.radians(max(8, min(36, species_count * 4)))
        p1 = self.polar_to_point(node.angle, node.radius)
        p2 = self.polar_to_point(node.angle - width_angle / 2, node.radius + span)
        p3 = self.polar_to_point(node.angle + width_angle / 2, node.radius + span)
        color = QColor(node.branch_color)
        color.setAlpha(95)
        item = self.scene.addPolygon(QPolygonF([p1, p2, p3]), QPen(QColor(node.branch_color), 1.5), QBrush(color))
        item.setZValue(2)
        self.register_node_graphic(node, item)

    def add_branch_line(self, node, x1, y1, x2, y2, pen):
        item = BranchLineItem(node, self, x1, y1, x2, y2, pen)
        self.scene.addItem(item)
        self.register_node_graphic(node, item)
        return item

    def node_pen(self, node):
        pen = QPen(QColor(node.branch_color), 3)
        if node in self.selected_nodes:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(4)
        return pen

    def should_draw_label(self, node):
        if not node.name:
            return False
        if self.hide_internal_names and not node.is_visible_leaf():
            return False
        return True

    def add_node_label(self, node, x, y):
        label = NodeLabelItem(node, self, self.node_label_text(node))
        if node in self.selected_nodes:
            label.setDefaultTextColor(QColor("#111827"))
        label.setPos(x, y)
        self.scene.addItem(label)
        self.node_items[node] = label
        self.register_node_graphic(node, label)
        return label

    def position_rectangular_label(self, label, branch_start_x, branch_end_x, branch_y):
        text_rect = label.boundingRect()
        label_x = branch_start_x + 6
        if branch_end_x - branch_start_x > text_rect.width() + 16:
            label_x = branch_start_x + 6
        else:
            label_x = max(branch_start_x + 2, branch_end_x - text_rect.width() - 8)

        if self.label_position_mode == "mixed" and "\n" in label.toPlainText():
            label_y = branch_y - text_rect.height() / 2
        else:
            label_y = branch_y - text_rect.height() - 6
        label.setPos(label_x, label_y)

    def position_leaf_label(self, label, anchor_x, branch_y):
        text_rect = label.boundingRect()
        if self.label_position_mode == "mixed" and "\n" in label.toPlainText():
            label_y = branch_y - text_rect.height() / 2
        else:
            label_y = branch_y - text_rect.height() / 2
        label.setPos(anchor_x + 8, label_y)

    def add_node_handle(self, node, x, y):
        handle = NodeHandleItem(node, self, x, y)
        if node in self.selected_nodes:
            handle.setBrush(QBrush(QColor("#FFF4C2")))
            handle.setRect(-6, -6, 12, 12)
        self.scene.addItem(handle)
        self.register_node_graphic(node, handle)
        return handle

    def node_at(self, scene_pos, exclude=None):
        if exclude is None:
            excluded_nodes = set()
        elif isinstance(exclude, (list, set, tuple)):
            excluded_nodes = set(exclude)
        else:
            excluded_nodes = {exclude}
        snap = 36
        hit_rect = QRectF(scene_pos.x() - snap, scene_pos.y() - snap, snap * 2, snap * 2)
        items = self.scene.items(hit_rect)
        for item in items:
            if isinstance(item, NodeLabelItem) and item.node not in excluded_nodes:
                return item.node
            if isinstance(item, NodeHandleItem) and item.node not in excluded_nodes:
                return item.node
            if isinstance(item, BranchLineItem) and item.node not in excluded_nodes:
                return item.node
        nearest = None
        nearest_distance = snap + 1
        for node in self.node_graphics.keys():
            if node in excluded_nodes:
                continue
            distance = math.hypot(node.computed_x - scene_pos.x(), node.computed_y - scene_pos.y())
            if distance < nearest_distance:
                nearest = node
                nearest_distance = distance
        if nearest is not None:
            return nearest
        return None

    def node_from_graphic_item(self, item):
        if isinstance(item, (NodeLabelItem, NodeHandleItem, BranchLineItem)):
            return item.node
        return None

    def select_nodes_in_scene_rect(self, scene_rect, additive=True):
        nodes = []
        for item in self.scene.items(scene_rect):
            node = self.node_from_graphic_item(item)
            if node is not None and node not in nodes:
                nodes.append(node)
        if not nodes:
            return
        if additive:
            self.selected_nodes.update(nodes)
        else:
            self.selected_nodes = set(nodes)
        self.selected_node = nodes[-1]
        display_name = self.selected_node.name if self.selected_node.name else "（空白无名字节点）"
        self.lbl_selected.setText(f"当前选中：{display_name}；多选 {len(self.selected_nodes)} 个节点")
        self.node_group.setEnabled(True)
        self.edit_name.blockSignals(True)
        self.edit_name.setText(self.selected_node.name)
        self.edit_name.blockSignals(False)
        self.redraw_tree()

    def select_node(self, node, redraw=True, additive=False, preserve_existing=False):
        if node is None:
            self.selected_node = None
            self.selected_nodes.clear()
        elif preserve_existing:
            self.selected_node = node
        elif additive:
            if node in self.selected_nodes:
                self.selected_nodes.remove(node)
                self.selected_node = next(iter(self.selected_nodes), None)
            else:
                self.selected_nodes.add(node)
                self.selected_node = node
        else:
            self.selected_node = node
            self.selected_nodes = {node}

        panel_node = self.selected_node
        if panel_node is None:
            self.lbl_selected.setText("未选中任何节点")
            self.node_group.setEnabled(False)
        else:
            display_name = panel_node.name if panel_node.name else "（空白无名字节点）"
            if len(self.selected_nodes) > 1:
                self.lbl_selected.setText(f"当前选中：{display_name}；多选 {len(self.selected_nodes)} 个节点")
            else:
                self.lbl_selected.setText(f"当前选中：{display_name}")
            self.node_group.setEnabled(True)
            self.edit_name.blockSignals(True)
            self.edit_name.setText(panel_node.name)
            self.edit_name.blockSignals(False)
            self.slider_length.blockSignals(True)
            self.slider_length.setValue(max(20, min(500, panel_node.branch_length)))
            self.slider_length.blockSignals(False)
            self.cb_hide_children.blockSignals(True)
            self.cb_hide_children.setChecked(panel_node.hide_children)
            self.cb_hide_children.blockSignals(False)
        if redraw:
            self.redraw_tree()

    def hover_node(self, node):
        if node is None:
            return
        self.selected_node = node
        if not self.selected_nodes:
            self.selected_nodes = {node}
        display_name = node.name if node.name else "（空白无名字节点）"
        self.lbl_selected.setText(f"鼠标悬停：{display_name}")
        self.node_group.setEnabled(True)

    def reparent_node(self, node, new_parent):
        self.reparent_nodes(node, new_parent)

    def reparent_nodes(self, dragged_node, new_parent):
        if new_parent is None:
            self.redraw_tree()
            return

        moving_nodes = list(self.selected_nodes) if dragged_node in self.selected_nodes else [dragged_node]
        moving_nodes = [node for node in moving_nodes if node is not self.root and node is not new_parent]
        if not moving_nodes:
            self.redraw_tree()
            return

        blocked = [node for node in moving_nodes if new_parent.is_descendant_of(node)]
        if blocked:
            self.redraw_tree()
            return

        self.push_undo()
        for node in moving_nodes:
            new_parent.add_child(node)
        self.selected_nodes = set(moving_nodes)
        self.selected_node = dragged_node if dragged_node in self.selected_nodes else moving_nodes[0]
        self.redraw_tree()

    def delete_nodes(self, anchor_node=None):
        if isinstance(anchor_node, bool):
            anchor_node = None
        targets = self.selected_copy_roots() if anchor_node is None or anchor_node in self.selected_nodes else [anchor_node]
        targets = [node for node in targets if node is not self.root]
        if not targets:
            return
        self.close_active_name_editor()
        self.clear_drop_hint()
        self.drag_roots = []
        self.drag_delta = QPointF(0, 0)
        QTimer.singleShot(0, lambda targets=tuple(targets): self._delete_nodes_impl(targets))

    def _delete_nodes_impl(self, targets):
        alive_targets = [node for node in targets if isinstance(node, TreeNode) and node is not self.root]
        if not alive_targets:
            return
        self.push_undo()
        fallback = None
        for node in alive_targets:
            if node.parent is not None and node in node.parent.children:
                fallback = node.parent
                node.parent.children.remove(node)
                node.parent = None
        self.selected_nodes = set()
        self.selected_node = fallback or self.root
        self.select_node(self.selected_node)

    def edit_node_name(self, node):
        self.close_active_name_editor()

        editor = QLineEdit(node.name)
        editor.setFont(QFont("Microsoft YaHei", 10))
        editor.selectAll()
        editor.setMinimumWidth(max(120, len(node.name) * 12 + 36))
        editor.setStyleSheet("background: white; border: 1px solid #4A90E2; padding: 2px 4px;")
        proxy = self.scene.addWidget(editor)
        proxy.setZValue(100)
        label = self.node_items.get(node)
        if label is not None:
            proxy.setPos(label.sceneBoundingRect().topLeft())
        else:
            proxy.setPos(node.computed_x + 8, node.computed_y - 18)
        proxy.node_ref = node
        proxy.editor_ref = editor
        self.active_name_editor = proxy

        committed = {"done": False}

        def commit():
            if committed["done"]:
                return
            committed["done"] = True
            self.active_name_editor = None
            try:
                if proxy.scene() is self.scene:
                    self.scene.removeItem(proxy)
            except RuntimeError:
                pass
            self.set_node_name(node, editor.text().strip())

        editor.editingFinished.connect(commit)
        editor.returnPressed.connect(commit)
        QTimer.singleShot(0, editor.setFocus)

    def close_active_name_editor(self, commit=False):
        proxy = self.active_name_editor
        self.active_name_editor = None
        if proxy is None:
            return
        if commit:
            try:
                editor = getattr(proxy, "editor_ref", None)
                node = getattr(proxy, "node_ref", None)
                if editor is not None and node is not None:
                    node.name = editor.text().strip()
            except RuntimeError:
                pass
        try:
            widget = proxy.widget()
            if widget is not None:
                widget.blockSignals(True)
        except RuntimeError:
            return
        try:
            if proxy.scene() is self.scene:
                self.scene.removeItem(proxy)
        except RuntimeError:
            return

    def set_node_name(self, node, name):
        if node.name == name:
            return
        self.push_undo()
        node.name = name
        if node is self.selected_node:
            self.edit_name.blockSignals(True)
            self.edit_name.setText(name)
            self.edit_name.blockSignals(False)
        QTimer.singleShot(0, self.redraw_tree)

    def rename_selected_node(self):
        if self.selected_node is None:
            return
        name = self.edit_name.text().strip()
        self.set_node_name(self.selected_node, name)

    def diy_add_node(self):
        if self.selected_node:
            self.push_undo()
            new_name = f"新进化分支_{len(self.selected_node.children) + 1}"
            new_node = TreeNode(new_name, branch_length=100, branch_color=self.selected_node.branch_color)
            self.selected_node.add_child(new_node)
            self.selected_node.hide_children = False
            self.select_node(new_node)

    def diy_add_blank_node(self):
        if self.selected_node:
            self.push_undo()
            new_node = TreeNode("", branch_length=100, branch_color=self.selected_node.branch_color)
            self.selected_node.add_child(new_node)
            self.selected_node.hide_children = False
            self.select_node(new_node)

    def diy_change_color(self):
        if self.selected_node:
            self.change_node_color(self.selected_node)

    def diy_change_text_color(self):
        if self.selected_node:
            self.change_node_text_color(self.selected_node)

    def diy_change_subtree_color(self):
        if self.selected_node:
            self.change_subtree_branch_color(self.selected_node)

    def change_node_color(self, node):
        if node:
            color = QColorDialog.getColor(QColor(node.branch_color), self, "选择分支线条颜色")
            if color.isValid():
                self.push_undo()
                targets = self.selected_nodes if node in self.selected_nodes else {node}
                for target in targets:
                    target.branch_color = color.name()
                    target.color = color.name()
                self.redraw_tree()

    def change_node_text_color(self, node):
        if node:
            color = QColorDialog.getColor(QColor(node.text_color), self, "选择文本颜色")
            if color.isValid():
                self.push_undo()
                targets = self.selected_nodes if node in self.selected_nodes else {node}
                for target in targets:
                    target.text_color = color.name()
                self.redraw_tree()

    def change_subtree_branch_color(self, node):
        if node:
            color = QColorDialog.getColor(QColor(node.branch_color), self, "统一子分支颜色")
            if color.isValid():
                self.push_undo()
                for target in node.descendants():
                    target.branch_color = color.name()
                    target.color = color.name()
                self.redraw_tree()

    def diy_change_clade_color(self):
        if self.selected_node:
            self.change_node_clade_color(self.selected_node)

    def change_node_clade_color(self, node):
        if node:
            color = QColorDialog.getColor(QColor(node.clade_color or node.branch_color), self, "选择单系群背景色")
            if color.isValid():
                self.push_undo()
                node.clade_color = color.name()
                self.redraw_tree()

    def diy_clear_clade_color(self):
        if self.selected_node:
            self.clear_node_clade_color(self.selected_node)

    def clear_node_clade_color(self, node):
        if node:
            self.push_undo()
            node.clade_color = None
            self.redraw_tree()

    def diy_change_length(self, value):
        if self.selected_node:
            self.push_undo()
            targets = self.selected_nodes or {self.selected_node}
            for node in targets:
                node.branch_length = value
            self.redraw_tree()

    def diy_toggle_hide_children(self, state):
        if self.selected_node:
            self.push_undo()
            targets = self.selected_nodes or {self.selected_node}
            for node in targets:
                node.hide_children = state == Qt.CheckState.Checked.value
            self.redraw_tree()

    def toggle_align_right(self, state):
        self.push_undo()
        self.align_right = state == Qt.CheckState.Checked.value
        self.redraw_tree()

    def toggle_internal_names(self, state):
        self.push_undo()
        self.hide_internal_names = state == Qt.CheckState.Checked.value
        self.redraw_tree()

    def change_layout(self):
        self.push_undo()
        self.layout_mode = self.cmb_layout.currentData()
        self.cb_align.setEnabled(self.layout_mode == "rectangular")
        self.redraw_tree()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_nodes()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self.copy_selected_subtrees()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_from_clipboard()
            event.accept()
            return
        super().keyPressEvent(event)

    def paste_from_clipboard(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        parent = self.selected_node or self.root
        nodes = self.nodes_from_clipboard_text(text)
        if not nodes:
            return
        self.push_undo()
        for node in nodes:
            parent.add_child(node)
        parent.hide_children = False
        self.selected_nodes = set(nodes)
        self.selected_node = nodes[-1]
        self.redraw_tree()

    def copy_selected_subtrees(self):
        roots = self.selected_copy_roots()
        if not roots:
            return
        payload = {
            "type": "diy-evolution-tree-nodes",
            "nodes": [self.serialize_node(node) for node in roots],
        }
        QApplication.clipboard().setText("DIY_EVOLUTION_TREE_JSON\n" + json.dumps(payload, ensure_ascii=False))

    def selected_copy_roots(self):
        selected = list(self.selected_nodes)
        roots = []
        for node in selected:
            if not any(node.is_descendant_of(other) for other in selected if other is not node):
                roots.append(node)
        return roots

    def nodes_from_clipboard_text(self, text):
        if text.startswith("DIY_EVOLUTION_TREE_JSON\n"):
            try:
                payload = json.loads(text.split("\n", 1)[1])
                if payload.get("type") == "diy-evolution-tree-nodes":
                    return [self.deserialize_node(item) for item in payload.get("nodes", [])]
            except (TypeError, ValueError, json.JSONDecodeError):
                return []
        return self.nodes_from_text(text, show_empty_warning=False)

    def change_node_spacing(self, value):
        self.push_undo()
        self.node_spacing = value
        self.redraw_tree()

    def toggle_auto_branch_length(self, state):
        self.push_undo()
        self.auto_branch_length = state == Qt.CheckState.Checked.value
        self.redraw_tree()

    def change_label_wrap_lines(self):
        self.push_undo()
        self.label_wrap_lines = self.cmb_wrap_lines.currentData()
        self.redraw_tree()

    def change_label_position_mode(self):
        self.push_undo()
        self.label_position_mode = self.cmb_label_position.currentData()
        self.redraw_tree()

    def reset_to_single_node(self):
        self.push_undo()
        self.root = TreeNode("起始节点", 0)
        self.select_node(self.root)

    def serialize_node(self, node):
        return {
            "name": node.name,
            "branch_length": node.branch_length,
            "branch_color": node.branch_color,
            "text_color": node.text_color,
            "color": node.branch_color,
            "clade_color": node.clade_color,
            "hide_children": node.hide_children,
            "manual_dx": node.manual_dx,
            "manual_dy": node.manual_dy,
            "children": [self.serialize_node(child) for child in node.children],
        }

    def deserialize_node(self, data):
        branch_color = data.get("branch_color", data.get("color", "#7EC8E3"))
        text_color = data.get("text_color", "#111827")
        node = TreeNode(
            data.get("name", ""),
            int(data.get("branch_length", 100)),
            branch_color,
            text_color,
        )
        node.manual_dx = float(data.get("manual_dx", 0))
        node.manual_dy = float(data.get("manual_dy", 0))
        node.clade_color = data.get("clade_color")
        node.hide_children = bool(data.get("hide_children", False))
        for child_data in data.get("children", []):
            node.add_child(self.deserialize_node(child_data))
        return node

    def save_tree_file(self):
        self.close_active_name_editor(commit=True)
        path, _ = QFileDialog.getSaveFileName(self, "保存进化树工程", self.default_json_filename(), "Tree JSON (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            self.save_state_to_path(path)
        except OSError as exc:
            QMessageBox.warning(self, "保存失败", f"无法保存文件：\n{exc}")
            return
        QMessageBox.information(self, "保存完成", f"工程已保存到：\n{path}")

    def open_tree_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开进化树工程", "", "Tree JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)
            data["root"]
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "打开失败", f"文件格式不正确或无法读取：\n{exc}")
            return

        self.push_undo()
        try:
            self.apply_state(data)
        except (KeyError, TypeError, ValueError) as exc:
            self.undo()
            QMessageBox.warning(self, "打开失败", f"文件格式不正确：\n{exc}")

    def export_pdf(self):
        self.close_active_name_editor(commit=True)
        path, _ = QFileDialog.getSaveFileName(self, "导出进化树 PDF", self.default_pdf_filename(), "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        writer = QPdfWriter(path)
        writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        writer.setResolution(300)

        painter = QPainter(writer)
        if not painter.isActive():
            QMessageBox.warning(self, "导出失败", "无法创建 PDF 文件，请检查保存路径。")
            return

        source = self.scene.itemsBoundingRect().adjusted(-35, -35, 35, 35)
        target = QRectF(writer.pageLayout().paintRectPixels(writer.resolution()))
        self.scene.render(painter, target, source, Qt.AspectRatioMode.KeepAspectRatio)
        painter.end()
        QMessageBox.information(self, "导出完成", f"PDF 已保存到：\n{path}")

    def closeEvent(self, event):
        try:
            self.close_active_name_editor(commit=True)
            path = self.autosave_json()
        except OSError as exc:
            QMessageBox.warning(self, "自动保存失败", f"退出前无法保存自动备份：\n{exc}")
            event.ignore()
            return
        event.accept()

    def add_names_to_selected(self):
        parent = self.selected_node or self.root
        nodes = self.nodes_from_text(self.txt_names.toPlainText())
        if not nodes:
            return
        self.push_undo()
        for node in nodes:
            parent.add_child(node)
        parent.hide_children = False
        self.select_node(parent)

    def rebuild_tree_from_paste(self):
        nodes = self.nodes_from_text(self.txt_names.toPlainText())
        if not nodes:
            return
        self.push_undo()
        self.root = TreeNode("DIY Root", 0)
        for node in nodes:
            self.root.add_child(node)
        self.select_node(self.root)

    def nodes_from_text(self, text, show_empty_warning=True):
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            if show_empty_warning:
                QMessageBox.information(self, "没有名单", "请先粘贴至少一行节点名称。")
            return []

        root_nodes = []
        stack = []
        for raw_line in lines:
            indent = len(raw_line) - len(raw_line.lstrip(" \t"))
            level = indent // 2
            name = raw_line.strip()
            node = TreeNode(name, 110)

            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].add_child(node)
            else:
                root_nodes.append(node)
            stack.append((level, node))

        return root_nodes


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DIYEvolutionTree()
    window.show()
    sys.exit(app.exec())
