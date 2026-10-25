"""
树形视图操作模块

该模块包含处理树形视图相关操作的代码，负责树的生成、节点展开收起、
节点选择和状态维护等功能。支持复杂的树状态保持逻辑，允许用户
在重新加载时保留节点的展开/收起和选择状态。

Classes:
    TreeOperations: 处理树形视图操作的类
"""

from pathlib import Path
from ai_code_context_helper.config import CHECK_MARK
from ai_code_context_helper.file_utils import normalize_path
import os
import re


class TreeOperations:
    """处理树形视图操作的类"""

    def __init__(self, parent):
        self.parent = parent
        self._last_clicked_item = None
        self._last_click_time = 0
        self._is_dragging = False  # 跟踪是否在拖动
        self._confirmed_selections = set()  # 存储已确认的选择
        self._last_item_toggle_state = {}  # 存储项目在拖动开始时的状态

    def on_tree_button_down(self, event):
        """处理鼠标按下事件，开始可能的拖动操作"""

        self.parent.root.focus()
        item = self.parent.tree.identify_row(event.y)
        if not item:
            return

        column = self.parent.tree.identify_column(event.x)

        if column == "#1":  # 点击的是复选框列
            # 复选框列的点击处理保持不变
            values = self.parent.tree.item(item, "values")
            if values and values[0] == "✓":
                self.parent.tree.item(item, values=("",))
                self.parent.checked_items.discard(item)
                self.parent.tree.item(item, tags=("gray",))
                self._uncheck_all_children(item)
            else:
                self.parent.tree.item(item, values=("✓",))
                self.parent.checked_items.add(item)
                self.parent.tree.item(item, tags=())
                self._check_all_children(item)
                self._ensure_parents_checked(item)
        elif self.parent.enable_easy_multiselect.get():  # 使用鼠标框选模式
            # 初始化拖动状态
            self._is_dragging = True
            self._last_item = item  # 记录最后处理的项目
            self._previous_item = None  # 记录倒数第二个处理的项目
            self._item_positions = {}  # 用于跟踪项目在树中的顺序

            # 为了判断方向，记录所有可见项目的顺序
            for i, visible_item in enumerate(self._get_visible_items()):
                self._item_positions[visible_item] = i

            # 切换初始项的选择状态
            if item in self.parent.tree.selection():
                self.parent.tree.selection_remove(item)
            else:
                self.parent.tree.selection_add(item)

            # 绑定拖动事件
            self.parent.tree.bind("<B1-Motion>", self._on_tree_drag)

            # 阻止事件继续传播，防止默认的selection_set行为
            return "break"

    def _get_visible_items(self):
        """获取当前可见的所有树项目"""
        visible_items = []

        def collect_visible(parent=""):
            for item in self.parent.tree.get_children(parent):
                visible_items.append(item)
                if self.parent.tree.item(item, "open"):
                    collect_visible(item)

        collect_visible()
        return visible_items

    def on_tree_double_click(self, event):
        """处理双击事件，确保展开目录并加载内容"""
        # 获取点击的行
        item_id = self.parent.tree.identify_row(event.y)
        if not item_id:
            return

        # 获取项目路径
        item_path = None
        for path, tree_id in self.parent.tree_items.items():
            if tree_id == item_id:
                item_path = path
                break

        # 如果是目录
        if item_path and Path(item_path).is_dir():
            # 切换展开状态
            is_open = self.parent.tree.item(item_id, "open")

            if not is_open:
                # 展开并强制加载子内容
                self.parent.tree.item(item_id, open=True)
                self._load_children_content(item_id, item_path)
                # 更新展开状态
                self.parent._save_expanded_state()
            else:
                # 关闭节点
                self.parent.tree.item(item_id, open=False)
                # 更新展开状态
                self.parent._save_expanded_state()

            # 防止默认处理
            return "break"

    def generate_tree(self, preserve_state=False):
        """生成并显示目录树结构

        Args:
            preserve_state: 是否保留展开状态，True保留，False只展开根节点
        """
        print(f"===== 生成树调用，preserve_state={preserve_state} =====")

        directory = self.parent.dir_path.get().strip()
        directory_path = Path(directory)
        if not directory or not directory_path.is_dir():
            print(f"无效目录: {directory}")
            self.parent.status_var.set(self.parent.texts["error_invalid_dir"])
            return

        # 标准化路径
        directory = normalize_path(directory)
        print(f"生成目录 '{directory}' 的树")

        old_tree_items = {}
        old_checked_items = set()
        old_open_items = set()

        # 定义一个变量控制是否使用保存的展开状态
        use_saved_expansion = False
        use_old_state = False

        # 根据preserve_state决定是否使用保存的展开状态
        if preserve_state and directory in self.parent.settings.expanded_states:
            print(
                f"使用保存的展开状态: {self.parent.settings.expanded_states[directory]}"
            )
            self._paths_to_expand = self.parent.settings.expanded_states.get(
                directory, []
            )
            use_saved_expansion = True
        elif preserve_state and self.parent.tree_items:
            # 使用当前会话状态
            print("使用当前会话的树状态")
            old_tree_items = self.parent.tree_items.copy()
            old_checked_items = self.parent.checked_items.copy()
            old_open_items = {
                item_id
                for item_id in self.parent.tree_items.values()
                if self.parent.tree.item(item_id, "open")
            }
            use_old_state = True  # 新增：标记使用旧状态
        else:
            # 重置状态，只展开根节点
            print("重置状态，只保留根节点展开")
            self._paths_to_expand = ["."]
            # 更新设置中的展开状态
            if directory in self.parent.settings.expanded_states:
                self.parent.settings.expanded_states[directory] = ["."]
                self.parent.settings.settings_changed = True

        # 清空当前树
        print("清空当前树")
        self.parent.tree.delete(*self.parent.tree.get_children())
        self.parent.tree_items = {}
        self.parent.checked_items = set()
        self.parent.status_var.set(self.parent.texts["generating_tree"])
        self.parent.root.update_idletasks()

        try:
            # 创建根节点
            dir_name = directory_path.name
            if not dir_name:
                dir_name = str(directory_path)

            print(f"创建根节点: {dir_name}")
            root_id = self.parent.tree.insert(
                "", "end", text=dir_name, open=True, values=(CHECK_MARK,)
            )
            self.parent.tree_items[str(directory_path)] = root_id
            self.parent.checked_items.add(root_id)

            # 填充树 - 修改这部分代码，根据状态选择填充方法
            if use_old_state:
                # 使用保留状态的填充方法
                print("使用状态保留模式填充树")
                self._populate_tree_with_state(
                    directory_path,
                    root_id,
                    0,
                    old_tree_items,
                    old_checked_items,
                    old_open_items,
                )
            else:
                # 使用标准填充方法
                print("使用标准模式填充树")
                self._populate_tree(directory_path, root_id, 0)

            # 确保根节点展开
            self.parent.tree.item(root_id, open=True)

            # 在树生成完成后，如果需要恢复保存的展开状态
            if (
                use_saved_expansion
                and hasattr(self, "_paths_to_expand")
                and self._paths_to_expand
            ):
                print(f"恢复保存的展开状态: {self._paths_to_expand}")
                self._restore_expanded_state(directory_path)
            else:
                print("无需恢复展开状态")

            self.parent.status_var.set(
                self.parent.texts["status_tree_generated"].format(directory)
            )
            print("目录树生成完成")
        except Exception as e:
            print(f"生成树时出错: {str(e)}")
            import traceback

            traceback.print_exc()
            self.parent.status_var.set(self.parent.texts["error_msg"].format(str(e)))

    def _restore_expanded_state(self, root_path):
        """从保存的路径列表恢复展开状态"""
        if not hasattr(self, "_paths_to_expand") or not self._paths_to_expand:
            print("没有找到要展开的路径")
            return

        # 打印初始的展开路径列表
        print(f"初始展开路径列表: {self._paths_to_expand}")

        # 过滤掉可能的非相对路径，确保只使用属于当前项目的路径
        valid_paths = []

        for path in self._paths_to_expand:
            # 确保是相对路径或根目录标记
            if path == "." or (not os.path.isabs(path)):
                valid_paths.append(path)

        print(f"过滤后的有效路径: {valid_paths}")

        if not valid_paths:
            print("没有有效的相对路径需要展开")
            return

        # 按照路径长度排序，确保先展开上层目录
        sorted_paths = sorted(valid_paths, key=lambda p: len(p.split("\\")))

        print(f"将要展开的路径: {sorted_paths}")

        # 首先确保根节点展开
        root_items = self.parent.tree.get_children()
        if root_items:
            self.parent.tree.item(root_items[0], open=True)

        # 处理所有路径
        for rel_path in sorted_paths:
            try:
                # 跳过根目录标记，因为已处理
                if rel_path == ".":
                    continue

                print(f"正在处理路径: {rel_path}")

                # 如果是单级目录（没有斜杠），则直接在根目录下寻找
                if not "\\" in rel_path and not "/" in rel_path:
                    # 尝试在根节点的子项中查找
                    root_id = None
                    for path, tree_id in self.parent.tree_items.items():
                        if str(path) == str(root_path):
                            root_id = tree_id
                            break

                    if root_id:
                        for child_id in self.parent.tree.get_children(root_id):
                            child_text = self.parent.tree.item(child_id, "text")
                            if child_text == rel_path:
                                # 找到了匹配项，展开它并确保加载其内容
                                self.parent.tree.item(child_id, open=True)

                                # 关键部分：确保子节点已加载
                                self._ensure_children_loaded(child_id)

                                # 检查是否需要触发展开事件
                                child_path = None
                                for p, tid in self.parent.tree_items.items():
                                    if tid == child_id:
                                        child_path = p
                                        break

                                if child_path:
                                    # 确保目录内容已经加载
                                    has_dummy = False
                                    for grandchild in self.parent.tree.get_children(
                                        child_id
                                    ):
                                        tags = self.parent.tree.item(grandchild, "tags")
                                        if tags and "dummy" in tags:
                                            has_dummy = True
                                            break

                                    if has_dummy:
                                        # 如果有dummy节点，需要触发on_tree_open事件来加载内容
                                        print(
                                            f"检测到 {rel_path} 有dummy节点，正在加载内容..."
                                        )
                                        # 手动调用on_tree_open方法来加载内容
                                        self.parent.tree.focus(child_id)
                                        self.on_tree_open(None)

                                print(f"已成功展开单级目录: {rel_path}")
                                break
                    continue

                # 构建完整路径
                full_path = root_path / rel_path

                # 检查路径是否存在于树中
                path_str = str(full_path)
                if path_str in self.parent.tree_items:
                    item_id = self.parent.tree_items[path_str]

                    # 展开所有父节点
                    parent_id = self.parent.tree.parent(item_id)
                    while parent_id:
                        self.parent.tree.item(parent_id, open=True)
                        # 确保子节点已加载
                        self._ensure_children_loaded(parent_id)
                        parent_id = self.parent.tree.parent(parent_id)

                    # 展开当前节点
                    self.parent.tree.item(item_id, open=True)
                    self._ensure_children_loaded(item_id)
                    print(f"已成功展开: {rel_path}")
                else:
                    print(f"未在树中找到路径: {path_str}，尝试逐级展开")
                    # 尝试逐级构建和展开路径
                    self._expand_path_by_parts(root_path, rel_path)
            except Exception as e:
                print(f"展开路径 {rel_path} 时出错: {str(e)}")
                import traceback

                traceback.print_exc()
                continue

    def _expand_path_by_parts(self, root_path, rel_path):
        """逐级展开路径"""
        parts = rel_path.split("\\")
        current_path = root_path
        current_id = None

        # 找到根节点ID
        for path, tree_id in self.parent.tree_items.items():
            if str(path) == str(root_path):
                current_id = tree_id
                break

        if not current_id:
            print(f"找不到根节点ID: {root_path}")
            return

        # 逐级展开
        for part in parts:
            if not part:  # 跳过空部分
                continue

            current_path = current_path / part

            # 检查当前路径是否存在
            if not current_path.exists() or not current_path.is_dir():
                print(f"路径不存在或不是目录: {current_path}")
                break

            # 展开当前父节点
            self.parent.tree.item(current_id, open=True)
            self._ensure_children_loaded(current_id)

            # 在子节点中查找下一级
            found = False
            for child_id in self.parent.tree.get_children(current_id):
                child_text = self.parent.tree.item(child_id, "text")
                if child_text == part:
                    current_id = child_id
                    found = True
                    break

            if not found:
                print(f"在树中找不到部分: {part}")
                break

        # 最后展开找到的节点
        if current_id:
            self.parent.tree.item(current_id, open=True)
            self._ensure_children_loaded(current_id)
            print(f"逐级展开成功: {rel_path}")

    def _properly_expand_node(self, item_id):
        """正确地展开一个节点，确保其内容被加载"""
        # 先检查是否需要加载子节点
        children = self.parent.tree.get_children(item_id)
        has_dummy = False

        for child in children:
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                has_dummy = True
                break

        if has_dummy:
            # 如果有dummy节点，需要先删除它们并加载真实内容
            for child in children:
                tags = self.parent.tree.item(child, "tags")
                if tags and "dummy" in tags:
                    self.parent.tree.delete(child)

            # 获取对应的路径，并加载其内容
            path = None
            for p, tree_id in self.parent.tree_items.items():
                if tree_id == item_id:
                    path = p
                    break

            if path:
                level = 0
                temp_id = item_id
                while temp_id != "":
                    parent = self.parent.tree.parent(temp_id)
                    if parent != "":
                        level += 1
                    temp_id = parent

                path_obj = Path(path)
                if path_obj.exists() and path_obj.is_dir():
                    # 使用_populate_tree加载子节点
                    self._populate_tree(path_obj, item_id, level)

        # 设置为展开状态
        self.parent.tree.item(item_id, open=True)

    def _ensure_children_loaded(self, item_id):
        """确保节点的子节点已经加载"""
        # 检查是否有未加载的子节点（dummy 节点）
        children = self.parent.tree.get_children(item_id)
        has_dummy = False

        for child in children:
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                has_dummy = True
                break

        if has_dummy:
            item_text = self.parent.tree.item(item_id, "text")
            print(f"正在加载节点 '{item_text}' 的子内容...")
            # 获取对应的路径
            path = None
            for p, tree_id in self.parent.tree_items.items():
                if tree_id == item_id:
                    path = p
                    break

            if path:
                # 保存当前的open状态
                was_open = self.parent.tree.item(item_id, "open")

                # 删除dummy节点
                for child in list(self.parent.tree.get_children(item_id)):
                    tags = self.parent.tree.item(child, "tags")
                    if tags and "dummy" in tags:
                        self.parent.tree.delete(child)

                # 计算当前节点的级别
                level = 0
                temp_id = item_id
                while temp_id != "":
                    parent = self.parent.tree.parent(temp_id)
                    if parent != "":
                        level += 1
                    temp_id = parent

                # 直接使用_populate_tree而不是_populate_tree_with_state
                # 因为我们要加载实际的文件系统内容
                self._populate_tree(Path(path), item_id, level)

                # 恢复open状态
                self.parent.tree.item(item_id, open=was_open)

                print(f"节点 '{item_text}' 的子内容已加载")
                return True

        return False

    def _populate_tree(self, directory_path, parent_id, level):
        """递归填充目录树视图"""
        # 导入需要的模块和配置
        from ai_code_context_helper.file_utils import get_file_stats, is_ignored_by_gitignore
        from ai_code_context_helper.config import CHECK_MARK
    
        max_depth = self.parent.max_depth.get()
        if max_depth > 0 and level >= max_depth:
            return

        try:
            entries = list(directory_path.iterdir())
        except PermissionError:
            error_id = self.parent.tree.insert(
                parent_id,
                "end",
                text=self.parent.texts["error_permission_denied"],
                values=("", "", ""),
            )
            self.parent.tree.item(error_id, tags=("gray",))
            return
        except Exception as e:
            error_id = self.parent.tree.insert(
                parent_id,
                "end",
                text=self.parent.texts["error_msg"].format(str(e)),
                values=("", "", ""),
            )
            self.parent.tree.item(error_id, tags=("gray",))
            return

        if not self.parent.show_hidden.get():
            entries = [
                e
                for e in entries
                if not e.name.startswith(".")
                and not (
                    os.name == "nt"
                    and e.is_file()
                    and bool(e.stat().st_file_attributes & 2)
                )
            ]

        # 应用.gitignore过滤
        if self.parent.use_gitignore.get():
            # 查找项目根目录
            project_root = normalize_path(self.parent.dir_path.get().strip())
        
            # 筛选条目
            filtered_entries = []
            for e in entries:
                if not is_ignored_by_gitignore(str(e), project_root):
                    filtered_entries.append(e)
            entries = filtered_entries

        # 应用文件过滤器
        filter_pattern = self.parent.file_filter.get().strip()
        if filter_pattern:
            try:
                pattern = re.compile(filter_pattern)
                entries = [e for e in entries if pattern.search(e.name)]
            except re.error:
                pass

        # 分离目录和文件
        dirs = []
        files = []

        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if entry.is_dir():
                if self.parent.show_folders.get():
                    dirs.append(entry)
            elif self.parent.show_files.get():
                files.append(entry)

        # 处理目录
        for d in dirs:
            item_id = self.parent.tree.insert(
                parent_id, 
                "end", 
                text=d.name, 
                values=(CHECK_MARK, "", ""),  # 目录不显示行数和大小
                open=False
            )
            self.parent.tree_items[str(d)] = item_id
            self.parent.checked_items.add(item_id)

            # 检查目录是否有内容
            has_contents = False
            try:
                next(d.iterdir(), None)
                has_contents = True
            except (PermissionError, OSError, StopIteration):
                pass

            # 如果有内容，添加一个dummy节点用于延迟加载
            if has_contents:
                self.parent.tree.insert(item_id, "end", text="", tags=("dummy",))

        # 处理文件
        for f in files:
            # 获取文件统计信息（行数和大小）
            lines, _, size_str = get_file_stats(str(f))
        
            # 插入文件节点，包含行数和大小信息
            item_id = self.parent.tree.insert(
                parent_id, 
                "end", 
                text=f.name,  # 只显示文件名
                values=(CHECK_MARK, str(lines) if lines > 0 else "", size_str)  # 在单独的列中显示行数和大小
            )
            self.parent.tree_items[str(f)] = item_id
            self.parent.checked_items.add(item_id)

    def _populate_tree_with_state(
        self,
        directory_path,
        parent_id,
        level,
        old_tree_items,
        old_checked_items,
        old_open_items,
    ):
        """带状态保留的目录树填充函数"""
        # 导入需要的模块和配置
        from ai_code_context_helper.file_utils import get_file_stats, is_ignored_by_gitignore
        from ai_code_context_helper.config import CHECK_MARK
    
        max_depth = self.parent.max_depth.get()
        if max_depth > 0 and level >= max_depth:
            return

        try:
            entries = list(directory_path.iterdir())
        except PermissionError:
            error_id = self.parent.tree.insert(
                parent_id,
                "end",
                text=self.parent.texts["error_permission_denied"],
                values=("", "", ""),
            )
            self.parent.tree.item(error_id, tags=("gray",))
            return
        except Exception as e:
            error_id = self.parent.tree.insert(
                parent_id,
                "end",
                text=self.parent.texts["error_msg"].format(str(e)),
                values=("", "", ""),
            )
            self.parent.tree.item(error_id, tags=("gray",))
            return

        if not self.parent.show_hidden.get():
            entries = [
                e
                for e in entries
                if not e.name.startswith(".")
                and not (
                    os.name == "nt"
                    and e.is_file()
                    and bool(e.stat().st_file_attributes & 2)
                )
            ]

        # 应用.gitignore过滤
        if self.parent.use_gitignore.get():
            # 查找项目根目录
            project_root = normalize_path(self.parent.dir_path.get().strip())
        
            # 筛选条目
            filtered_entries = []
            for e in entries:
                if not is_ignored_by_gitignore(str(e), project_root):
                    filtered_entries.append(e)
            entries = filtered_entries

        # 应用文件过滤器
        filter_pattern = self.parent.file_filter.get().strip()
        if filter_pattern:
            try:
                pattern = re.compile(filter_pattern)
                entries = [e for e in entries if pattern.search(e.name)]
            except re.error:
                pass

        # 分离目录和文件
        dirs = []
        files = []

        for entry in sorted(entries, key=lambda e: e.name.lower()):
            if entry.is_dir():
                if self.parent.show_folders.get():
                    dirs.append(entry)
            elif self.parent.show_files.get():
                files.append(entry)

        # 处理目录
        for d in dirs:
            path_str = str(d)

            # 查找旧状态
            old_id = None
            checked = True  # 默认值为 True
            is_open = False

            # 通过规范化路径查找旧项目ID
            for old_path, old_item_id in old_tree_items.items():
                # 只使用绝对路径比较，避免基于名称的错误匹配
                if os.path.abspath(old_path) == os.path.abspath(path_str):
                    old_id = old_item_id
                    checked = old_id in old_checked_items
                    is_open = old_id in old_open_items
                    break
                # 如果没有找到精确匹配，再尝试使用名称+父路径来识别
                elif os.path.basename(old_path) == d.name and os.path.basename(
                    os.path.dirname(old_path)
                ) == os.path.basename(os.path.dirname(path_str)):
                    old_id = old_item_id
                    checked = old_id in old_checked_items
                    is_open = old_id in old_open_items
                    break

            # 调试输出
            print(
                f"目录: {d.name}, 找到旧ID: {old_id is not None}, 勾选状态: {checked}"
            )

            # 插入目录节点
            item_id = self.parent.tree.insert(
                parent_id,
                "end",
                text=d.name,
                values=(CHECK_MARK if checked else "", "", ""),  # 目录不显示行数和大小
                open=is_open,
            )

            self.parent.tree_items[path_str] = item_id

            if checked:
                self.parent.checked_items.add(item_id)
            else:
                self.parent.tree.item(item_id, tags=("gray",))

            # 检查目录是否有内容
            has_contents = False
            try:
                next(d.iterdir(), None)
                has_contents = True
            except (PermissionError, OSError, StopIteration):
                pass

            # 处理子内容
            if has_contents:
                if is_open:
                    # 如果节点已展开，递归加载子内容
                    self._populate_tree_with_state(
                        d,
                        item_id,
                        level + 1,
                        old_tree_items,
                        old_checked_items,
                        old_open_items,
                    )
                else:
                    # 如果节点关闭，添加dummy节点用于延迟加载
                    self.parent.tree.insert(item_id, "end", text="", tags=("dummy",))

        # 处理文件
        for f in files:
            path_str = str(f)

            # 查找旧状态
            old_id = None
            checked = True  # 默认值为 True

            # 通过规范化路径查找旧项目ID
            for old_path, old_item_id in old_tree_items.items():
                # 只使用绝对路径比较，避免基于名称的错误匹配
                if os.path.abspath(old_path) == os.path.abspath(path_str):
                    old_id = old_item_id
                    checked = old_id in old_checked_items
                    break
                # 如果没有找到精确匹配，再尝试使用名称+父路径来识别
                elif os.path.basename(old_path) == f.name and os.path.basename(
                    os.path.dirname(old_path)
                ) == os.path.basename(os.path.dirname(path_str)):
                    old_id = old_item_id
                    checked = old_id in old_checked_items
                    break

            # 调试输出
            print(
                f"文件: {f.name}, 找到旧ID: {old_id is not None}, 勾选状态: {checked}"
            )
        
            # 获取文件统计信息（行数和大小）
            lines, _, size_str = get_file_stats(str(f))
        
            # 插入文件节点，包含行数和大小信息
            item_id = self.parent.tree.insert(
                parent_id, 
                "end", 
                text=f.name,  # 只显示文件名
                values=(CHECK_MARK if checked else "", str(lines) if lines > 0 else "", size_str)  # 在单独的列中显示行数和大小
            )

            self.parent.tree_items[path_str] = item_id

            if checked:
                self.parent.checked_items.add(item_id)
            else:
                self.parent.tree.item(item_id, tags=("gray",))

    def on_tree_open(self, event):
        """处理树节点展开事件，加载子节点内容"""
        try:
            # 获取当前被展开的项
            if event:
                item_id = self.parent.tree.focus()
            else:
                item_id = self.parent.tree.focus()

            if not item_id:
                return

            item_text = self.parent.tree.item(item_id, "text")
            print(f"处理树节点展开事件: {item_text}")

            # 获取对应的路径
            path = None
            for p, tree_id in self.parent.tree_items.items():
                if tree_id == item_id:
                    path = p
                    break

            if not path:
                print(f"无法找到节点 {item_text} 的路径")
                return

            # 强制加载子内容
            self._load_children_content(item_id, path)

            # 节点展开后立即保存展开状态
            print("节点展开，更新展开状态")
            self.parent._save_expanded_state()
            self.parent.settings.settings_changed = True
        except Exception as e:
            print(f"处理展开事件时发生错误: {str(e)}")
            import traceback

            traceback.print_exc()

    def _load_children_content(self, item_id, path_str):
        """强制加载节点的子内容"""
        # 检查是否有dummy节点
        children = self.parent.tree.get_children(item_id)

        for child in children:
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                self.parent.tree.delete(child)

        # 即使没有dummy节点，也强制重新加载内容
        path_obj = Path(path_str)
        if path_obj.exists() and path_obj.is_dir():
            # 计算当前节点的级别
            level = 0
            temp_id = item_id
            while temp_id != "":
                parent = self.parent.tree.parent(temp_id)
                if parent != "":
                    level += 1
                temp_id = parent

            # 删除所有现有子节点
            for child in list(self.parent.tree.get_children(item_id)):
                self.parent.tree.delete(child)

            # 重新加载内容
            print(f"正在重新加载 {path_obj} 的内容")
            self._populate_tree(path_obj, item_id, level)
            print(
                f"内容已重新加载，子节点数: {len(self.parent.tree.get_children(item_id))}"
            )

    def on_tree_close(self, event):
        """处理树节点关闭的事件"""
        # 节点关闭后立即保存展开状态
        print("节点关闭，更新展开状态")
        self.parent._save_expanded_state()
        # 标记设置已更改
        self.parent.settings.settings_changed = True

    def _on_tree_drag(self, event):
        """处理鼠标拖动事件，实现拖动选择/取消功能"""
        if not self.parent.enable_easy_multiselect.get() or not self._is_dragging:
            return

        # 获取当前鼠标下的项目
        item = self.parent.tree.identify_row(event.y)
        if not item or item == self._last_item:
            return

        # 检测是否是方向变化（反向拖动）
        if (
            self._previous_item
            and self._last_item in self._item_positions
            and item in self._item_positions
        ):
            # 通过比较前两个处理的项目的位置索引来确定方向
            prev_pos = self._item_positions[self._previous_item]
            last_pos = self._item_positions[self._last_item]
            curr_pos = self._item_positions[item]

            # 检测方向变化
            if (last_pos > prev_pos and curr_pos < last_pos) or (
                last_pos < prev_pos and curr_pos > last_pos
            ):
                # 如果是反向拖动，重新处理最后一个项目（也切换它的状态）
                if self._last_item in self.parent.tree.selection():
                    self.parent.tree.selection_remove(self._last_item)
                else:
                    self.parent.tree.selection_add(self._last_item)

        # 切换当前项目的状态
        if item in self.parent.tree.selection():
            self.parent.tree.selection_remove(item)
        else:
            self.parent.tree.selection_add(item)

        # 更新项目记录
        self._previous_item = self._last_item
        self._last_item = item

    def on_tree_button_up(self, event):
        """处理鼠标释放事件，完成拖动操作"""
        if not self.parent.enable_easy_multiselect.get():
            # 如果不使用多选模式，则返回
            return

        # 无条件解绑拖动事件，防止事件绑定累积
        self.parent.tree.unbind("<B1-Motion>")

        # 如果在拖动，结束拖动状态
        if self._is_dragging:
            self._is_dragging = False

            # 清理拖动状态相关变量
            if hasattr(self, "_last_item"):
                delattr(self, "_last_item")
            if hasattr(self, "_previous_item"):
                delattr(self, "_previous_item")
            if hasattr(self, "_item_positions"):
                delattr(self, "_item_positions")

        # 阻止事件继续传播，防止默认行为
        return "break"

    def _check_all_children(self, parent):
        """递归选中所有子项"""
        for child in self.parent.tree.get_children(parent):
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                continue

            self.parent.tree.item(child, values=(CHECK_MARK,))
            self.parent.checked_items.add(child)
            self.parent.tree.item(child, tags=())
            self._check_all_children(child)

    def _uncheck_all_children(self, parent):
        """递归取消选中所有子项"""
        for child in self.parent.tree.get_children(parent):
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                continue

            self.parent.tree.item(child, values=("",))
            self.parent.checked_items.discard(child)
            self.parent.tree.item(child, tags=("gray",))
            self._uncheck_all_children(child)

    def _ensure_parents_checked(self, item):
        """确保所有父项都被选中"""
        parent = self.parent.tree.parent(item)
        if parent:
            if parent not in self.parent.checked_items:
                self.parent.tree.item(parent, values=("✓",))
                self.parent.checked_items.add(parent)
                self.parent.tree.item(parent, tags=())
            self._ensure_parents_checked(parent)

    def _update_parent_check_state(self, parent):
        """更新父项的选中状态，基于子项的状态"""
        if parent:
            children = self.parent.tree.get_children(parent)
            any_checked = False

            for child in children:
                tags = self.parent.tree.item(child, "tags")
                if tags and "dummy" in tags:
                    continue

                if child in self.parent.checked_items:
                    any_checked = True
                    break

            if any_checked:
                if parent not in self.parent.checked_items:
                    self.parent.tree.item(parent, values=("✓",))
                    self.parent.checked_items.add(parent)
                    self.parent.tree.item(parent, tags=())
            else:
                self.parent.tree.item(parent, values=("",))
                self.parent.checked_items.discard(parent)
                self.parent.tree.item(parent, tags=("gray",))
                self._update_parent_check_state(self.parent.tree.parent(parent))

    def expand_all(self):
        """递归展开选中的目录及其所有子目录"""
        selected_items = self.parent.tree.selection()
        if not selected_items:
            return

        for item in selected_items:
            self._expand_item_recursively(item)

        self.parent.status_var.set("已完全展开选中的目录")

    def _expand_item_recursively(self, item):
        """递归展开单个项目及其所有子项"""
        self.parent.tree.item(item, open=True)

        children = self.parent.tree.get_children(item)
        if not children:
            return

        has_dummy = False
        for child in children:
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                has_dummy = True
                self.parent.tree.delete(child)

        if has_dummy:
            parent_path = None
            for path, tree_id in self.parent.tree_items.items():
                if tree_id == item:
                    parent_path = path
                    break

            if parent_path:
                level = 0
                temp_id = item
                while temp_id != "":
                    parent = self.parent.tree.parent(temp_id)
                    if parent != "":
                        level += 1
                    temp_id = parent

                is_parent_checked = item in self.parent.checked_items

                old_tree_items = self.parent.tree_items.copy()
                old_checked_items = self.parent.checked_items.copy()
                old_open_items = {
                    item_id
                    for item_id in self.parent.tree_items.values()
                    if self.parent.tree.item(item_id, "open")
                }
                self._populate_tree_with_state(
                    Path(parent_path),
                    item,
                    level,
                    old_tree_items,
                    old_checked_items,
                    old_open_items,
                )

                if not is_parent_checked:
                    self._uncheck_all_children(item)

        for child in self.parent.tree.get_children(item):
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                continue

            self._expand_item_recursively(child)
