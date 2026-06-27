import math
import sys

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QBrush, QFont, QPageSize, QPainter, QPainterPath, QPdfWriter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QGraphicsEllipseItem,
    QFormLayout,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QCheckBox,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class TreeNode:
    """A lightweight editable multi-child evolution-tree node."""

    def __init__(self, name, branch_length=120, color="#2C3E50"):
        self.name = name
        self.branch_length = branch_length
        self.color = color
        self.clade_color = None
        self.children = []
        self.parent = None
        self.hide_children = False

        self.computed_x = 0
        self.computed_y = 0
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


class NodeLabelItem(QGraphicsTextItem):
    """Clickable and draggable node label."""

    def __init__(self, node, main_window):
        super().__init__(node.name)
        self.node = node
        self.main_window = main_window
        self.drag_start = None
        self.dragging = False
        self.setFont(QFont("Microsoft YaHei", 10))
        self.setDefaultTextColor(QColor(node.color))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(10)

    def mousePressEvent(self, event):
        self.drag_start = event.scenePos()
        self.dragging = False
        self.main_window.select_node(self.node, redraw=False)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            event.ignore()
            return
        distance = (event.scenePos() - self.drag_start).manhattanLength()
        if distance > 4:
            self.dragging = True
            self.setPos(event.scenePos() - QPointF(12, 12))
            event.accept()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.dragging:
            target = self.main_window.node_at(event.scenePos(), exclude=self.node)
            self.main_window.reparent_node(self.node, target)
        else:
            self.main_window.select_node(self.node)
        self.drag_start = None
        self.dragging = False
        event.accept()


class NodeHandleItem(QGraphicsEllipseItem):
    """Small selectable node handle, useful for blank or hidden labels."""

    def __init__(self, node, main_window, x, y):
        super().__init__(-5, -5, 10, 10)
        self.node = node
        self.main_window = main_window
        self.drag_start = None
        self.dragging = False
        self.setPos(x, y)
        self.setBrush(QBrush(QColor("#FFFFFF")))
        self.setPen(QPen(QColor(node.color), 2))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(12)

    def mousePressEvent(self, event):
        self.drag_start = event.scenePos()
        self.dragging = False
        self.main_window.select_node(self.node, redraw=False)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        if self.drag_start is None:
            event.ignore()
            return
        distance = (event.scenePos() - self.drag_start).manhattanLength()
        if distance > 4:
            self.dragging = True
            self.setPos(event.scenePos())
            event.accept()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if self.dragging:
            target = self.main_window.node_at(event.scenePos(), exclude=self.node)
            self.main_window.reparent_node(self.node, target)
        else:
            self.main_window.select_node(self.node)
        self.drag_start = None
        self.dragging = False
        event.accept()


class TreeView(QGraphicsView):
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.main_window = parent

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if not item:
            self.main_window.select_node(None)
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self.scale(factor, factor)


class DIYEvolutionTree(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DIY 进化树可视化设计器 (iTOL 自由交互版)")
        self.resize(1320, 820)

        self.root = TreeNode("LUCA (始祖)", 0, "#2C3E50")
        node_a = TreeNode("原核生物支", 100, "#C0392B")
        node_b = TreeNode("真核生物支", 150, "#2980B9")
        self.root.add_child(node_a)
        self.root.add_child(node_b)
        node_a.add_child(TreeNode("古菌", 115, "#D35400"))
        node_a.add_child(TreeNode("细菌", 125, "#E74C3C"))
        node_b.add_child(TreeNode("植物界", 120, "#27AE60"))
        node_b.add_child(TreeNode("动物界", 180, "#8E44AD"))

        self.selected_node = None
        self.align_right = False
        self.hide_internal_names = False
        self.layout_mode = "rectangular"
        self.node_items = {}
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

        self.btn_export_pdf = QPushButton("导出 PDF")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        global_form.addRow(self.btn_export_pdf)
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

        self.btn_color = QPushButton("改变本节点树枝与文本颜色")
        self.btn_color.clicked.connect(self.diy_change_color)
        node_form.addRow(self.btn_color)

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
        self.scene.clear()
        self.node_items = {}
        self.max_tree_x = 0
        self.get_max_depth(self.root, 50)

        if self.layout_mode == "rectangular":
            self.layout_rectangular()
            self.draw_rectangular_backgrounds(self.root)
            self.draw_rectangular_node(self.root, 50)
        else:
            self.layout_radial()
            self.draw_radial_backgrounds(self.root)
            self.draw_radial_node(self.root)

        rect = self.scene.itemsBoundingRect().adjusted(-70, -70, 90, 70)
        self.scene.setSceneRect(rect)

    def get_max_depth(self, node, current_x):
        next_x = current_x + node.branch_length
        self.max_tree_x = max(self.max_tree_x, next_x)
        if not node.hide_children:
            for child in node.children:
                self.get_max_depth(child, next_x)

    def layout_rectangular(self):
        self.leaf_counter = 0
        self.layout_rectangular_node(self.root, 50)

    def layout_rectangular_node(self, node, parent_x):
        node.computed_x = parent_x + node.branch_length
        if node.is_visible_leaf():
            self.leaf_counter += 1
            node.computed_y = self.leaf_counter * 64
            node.leaf_span = (node.computed_y, node.computed_y)
            return

        for child in node.children:
            self.layout_rectangular_node(child, node.computed_x)
        ys = [child.computed_y for child in node.children]
        node.computed_y = sum(ys) / len(ys)
        node.leaf_span = (min(child.leaf_span[0] for child in node.children), max(child.leaf_span[1] for child in node.children))

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
        branch_item = self.scene.addLine(parent_x, current_y, true_x, current_y, pen)
        branch_item.setZValue(1)

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
            trunk = self.scene.addLine(true_x, child_y_min, true_x, child_y_max, QPen(QColor(node.color), 2))
            trunk.setZValue(1)
            for child in node.children:
                self.draw_rectangular_node(child, true_x)

        self.add_node_handle(node, true_x, current_y)
        if self.should_draw_label(node):
            if node.is_visible_leaf():
                self.add_node_label(node, current_x + 8, current_y - 13)
            else:
                label_x = max(parent_x + 6, (parent_x + true_x) / 2 - 28)
                self.add_node_label(node, label_x, current_y - 31)

    def draw_radial_node(self, node):
        if node.parent is not None:
            parent_point = QPointF(node.parent.computed_x, node.parent.computed_y)
            node_point = QPointF(node.computed_x, node.computed_y)
            branch = self.scene.addLine(parent_point.x(), parent_point.y(), node_point.x(), node_point.y(), self.node_pen(node))
            branch.setZValue(1)

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
        color = QColor(node.color)
        color.setAlpha(95)
        item = self.scene.addPolygon(triangle, QPen(QColor(node.color), 1.5), QBrush(color))
        item.setZValue(2)

    def draw_collapsed_triangle_radial(self, node):
        species_count = max(1, self.descendant_leaf_count(node))
        span = max(34, min(130, self.descendant_max_span(node) * 0.22))
        width_angle = math.radians(max(8, min(36, species_count * 4)))
        p1 = self.polar_to_point(node.angle, node.radius)
        p2 = self.polar_to_point(node.angle - width_angle / 2, node.radius + span)
        p3 = self.polar_to_point(node.angle + width_angle / 2, node.radius + span)
        color = QColor(node.color)
        color.setAlpha(95)
        item = self.scene.addPolygon(QPolygonF([p1, p2, p3]), QPen(QColor(node.color), 1.5), QBrush(color))
        item.setZValue(2)

    def node_pen(self, node):
        pen = QPen(QColor(node.color), 3)
        if node is self.selected_node:
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
        label = NodeLabelItem(node, self)
        label.setPos(x, y)
        self.scene.addItem(label)
        self.node_items[node] = label
        return label

    def add_node_handle(self, node, x, y):
        handle = NodeHandleItem(node, self, x, y)
        if node is self.selected_node:
            handle.setBrush(QBrush(QColor("#FFF4C2")))
            handle.setRect(-6, -6, 12, 12)
        self.scene.addItem(handle)
        return handle

    def node_at(self, scene_pos, exclude=None):
        items = self.scene.items(scene_pos)
        for item in items:
            if isinstance(item, NodeLabelItem) and item.node is not exclude:
                return item.node
            if isinstance(item, NodeHandleItem) and item.node is not exclude:
                return item.node
        return None

    def select_node(self, node, redraw=True):
        self.selected_node = node
        if node is None:
            self.lbl_selected.setText("未选中任何节点")
            self.node_group.setEnabled(False)
        else:
            display_name = node.name if node.name else "（空白无名字节点）"
            self.lbl_selected.setText(f"当前选中：{display_name}")
            self.node_group.setEnabled(True)
            self.edit_name.blockSignals(True)
            self.edit_name.setText(node.name)
            self.edit_name.blockSignals(False)
            self.slider_length.blockSignals(True)
            self.slider_length.setValue(max(20, min(500, node.branch_length)))
            self.slider_length.blockSignals(False)
            self.cb_hide_children.blockSignals(True)
            self.cb_hide_children.setChecked(node.hide_children)
            self.cb_hide_children.blockSignals(False)
        if redraw:
            self.redraw_tree()

    def reparent_node(self, node, new_parent):
        if new_parent is None or node is self.root:
            self.redraw_tree()
            return
        if new_parent.add_child(node):
            self.select_node(node)
        else:
            QMessageBox.warning(self, "无法连接", "不能把节点拖到自己或自己的后代下面。")
            self.redraw_tree()

    def rename_selected_node(self):
        if self.selected_node is None:
            return
        name = self.edit_name.text().strip()
        self.selected_node.name = name
        self.redraw_tree()

    def diy_add_node(self):
        if self.selected_node:
            new_name = f"新进化分支_{len(self.selected_node.children) + 1}"
            new_node = TreeNode(new_name, branch_length=100, color=self.selected_node.color)
            self.selected_node.add_child(new_node)
            self.selected_node.hide_children = False
            self.select_node(new_node)

    def diy_add_blank_node(self):
        if self.selected_node:
            new_node = TreeNode("", branch_length=100, color=self.selected_node.color)
            self.selected_node.add_child(new_node)
            self.selected_node.hide_children = False
            self.select_node(new_node)

    def diy_change_color(self):
        if self.selected_node:
            color = QColorDialog.getColor(QColor(self.selected_node.color), self, "选择树枝与文本颜色")
            if color.isValid():
                self.selected_node.color = color.name()
                self.redraw_tree()

    def diy_change_clade_color(self):
        if self.selected_node:
            color = QColorDialog.getColor(QColor(self.selected_node.clade_color or self.selected_node.color), self, "选择单系群背景色")
            if color.isValid():
                self.selected_node.clade_color = color.name()
                self.redraw_tree()

    def diy_clear_clade_color(self):
        if self.selected_node:
            self.selected_node.clade_color = None
            self.redraw_tree()

    def diy_change_length(self, value):
        if self.selected_node:
            self.selected_node.branch_length = value
            self.redraw_tree()

    def diy_toggle_hide_children(self, state):
        if self.selected_node:
            self.selected_node.hide_children = state == Qt.CheckState.Checked.value
            self.redraw_tree()

    def toggle_align_right(self, state):
        self.align_right = state == Qt.CheckState.Checked.value
        self.redraw_tree()

    def toggle_internal_names(self, state):
        self.hide_internal_names = state == Qt.CheckState.Checked.value
        self.redraw_tree()

    def change_layout(self):
        self.layout_mode = self.cmb_layout.currentData()
        self.cb_align.setEnabled(self.layout_mode == "rectangular")
        self.redraw_tree()

    def export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出进化树 PDF", "diy_evolution_tree.pdf", "PDF Files (*.pdf)")
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

    def add_names_to_selected(self):
        parent = self.selected_node or self.root
        nodes = self.nodes_from_text(self.txt_names.toPlainText())
        if not nodes:
            return
        for node in nodes:
            parent.add_child(node)
        parent.hide_children = False
        self.select_node(parent)

    def rebuild_tree_from_paste(self):
        nodes = self.nodes_from_text(self.txt_names.toPlainText())
        if not nodes:
            return
        self.root = TreeNode("DIY Root", 0, "#2C3E50")
        for node in nodes:
            self.root.add_child(node)
        self.select_node(self.root)

    def nodes_from_text(self, text):
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            QMessageBox.information(self, "没有名单", "请先粘贴至少一行节点名称。")
            return []

        root_nodes = []
        stack = []
        palette = ["#2E86AB", "#E67E22", "#27AE60", "#8E44AD", "#C0392B", "#16A085", "#7D3C98"]

        for index, raw_line in enumerate(lines):
            indent = len(raw_line) - len(raw_line.lstrip(" \t"))
            level = indent // 2
            name = raw_line.strip()
            node = TreeNode(name, 110, palette[index % len(palette)])

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
