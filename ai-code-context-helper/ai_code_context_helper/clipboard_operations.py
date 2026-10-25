"""
剪贴板操作模块

该模块负责与剪贴板相关的所有操作，包括复制文件路径、代码内容、
目录树结构等。提供智能格式化和自定义输出格式的功能，支持
将内容保存到文件。

Classes:
    ClipboardOperations: 处理剪贴板操作的类
"""

from tkinter import filedialog
from pathlib import Path
import os
import re
from ai_code_context_helper.file_utils import (
    read_file_content,
    is_text_file,
    normalize_path,
    is_ignored_by_gitignore,
)


class ClipboardOperations:
    """处理剪贴板操作的类"""

    def __init__(self, parent):
        self.parent = parent

    def copy_to_clipboard(self):
        """将选中的目录树文本表示复制到剪贴板"""
        text = self._get_tree_text()

        if text:
            self.parent.root.clipboard_clear()
            self.parent.root.clipboard_append(text)
        
            # 计算总行数
            total_lines = text.count("\n") + 1
        
            self.parent.status_var.set(
                f"{self.parent.texts['status_copied_to_clipboard']} | 共 {total_lines} 行"
            )
        else:
            self.parent.status_var.set(self.parent.texts["status_no_selection"])

    def _get_tree_text(self):
        """获取目录树的文本表示，只包含选中的且可见的项目"""
        text = ""

        root_items = self.parent.tree.get_children()
        if not root_items:
            return text

        root_item = root_items[0]
        if root_item in self.parent.checked_items:
            root_text = self.parent.tree.item(root_item, "text")
            text = root_text + "\n"
            text = self._build_tree_text(root_item, "", text)

        return text

    def _build_tree_text(self, parent_id, prefix, text):
        """递归构建目录树的文本表示"""
        is_open = self.parent.tree.item(parent_id, "open")

        children = self.parent.tree.get_children(parent_id)
        if not children or not is_open:
            return text

        checked_children = [c for c in children if c in self.parent.checked_items]
        if not checked_children:
            return text

        for i, child in enumerate(children):
            tags = self.parent.tree.item(child, "tags")
            if tags and "dummy" in tags:
                continue

            if child not in self.parent.checked_items:
                continue

            is_last = (i == len(children) - 1) or all(
                c not in self.parent.checked_items for c in children[i + 1 :]
            )

            if is_last:
                line_prefix = prefix + "└── "
                next_prefix = prefix + "    "
            else:
                line_prefix = prefix + "├── "
                next_prefix = prefix + "│   "

            item_text = self.parent.tree.item(child, "text")
            text += line_prefix + item_text + "\n"
            text = self._build_tree_text(child, next_prefix, text)

        return text

    def copy_path(self):
        """复制选中文件或目录的路径到剪贴板"""
        results, count = self.process_selected_files()

        if results:
            combined = "\n".join(results)
            self.parent.root.clipboard_clear()
            self.parent.root.clipboard_append(combined)
        
            # 计算总行数
            total_lines = combined.count("\n") + 1
        
            # 使用带行数的状态消息
            self.parent.status_var.set(
                self.parent.texts.get("status_paths_copied_with_lines", "已复制 {0} 个路径 | 共 {1} 行").format(
                    count, total_lines
                )
            )
        else:
            self.parent.status_var.set(self.parent.texts["status_no_paths"])

    def copy_code(self):
        """复制选中文件的代码内容到剪贴板"""

        def code_processor(path_obj):
            try:
                code = read_file_content(path_obj)
                return self.format_code(code)
            except:
                return None

        results, count = self.process_selected_files(code_processor)

        if results:
            combined = "\n\n".join(results)
            self.parent.root.clipboard_clear()
            self.parent.root.clipboard_append(combined)
        
            # 计算总行数
            total_lines = combined.count("\n") + 1
        
            # 使用带行数的状态消息
            self.parent.status_var.set(
                self.parent.texts.get("status_code_copied_with_lines", "已复制 {0} 个文件的代码 | 共 {1} 行").format(
                    count, total_lines
                )
            )
        else:
            self.parent.status_var.set(self.parent.texts["status_no_text_files"])

    def copy_both(self):
        """同时复制选中文件的路径和代码内容到剪贴板"""

        def both_processor(path_obj):
            try:
                code = read_file_content(path_obj)
                formatted_path = self.format_path(self.get_relative_path(path_obj))
                formatted_code = self.format_code(code)
                return f"{formatted_path}\n\n{formatted_code}\n\n\n\n"
            except:
                return None

        results, count = self.process_selected_files(both_processor)

        if results:
            combined = "".join(results)
            self.parent.root.clipboard_clear()
            self.parent.root.clipboard_append(combined)
        
            # 计算总行数
            total_lines = combined.count("\n") + 1
        
            # 使用带行数的状态消息
            self.parent.status_var.set(
                self.parent.texts.get("status_path_code_copied_with_lines", "已复制 {0} 个文件的路径和代码 | 共 {1} 行").format(
                    count, total_lines
                )
            )
        else:
            self.parent.status_var.set(self.parent.texts["status_no_text_files"])

    def copy_filename(self):
        """复制选中文件或目录的文件名到剪贴板"""
        selected_items = self.parent.tree.selection()
        if not selected_items:
            self.parent.status_var.set(self.parent.texts["status_no_selection"])
            return

        filenames = []
        for item in selected_items:
            if item not in self.parent.checked_items:
                continue

            # 查找item对应的路径
            path = None
            for p, tree_id in self.parent.tree_items.items():
                if tree_id == item:
                    path = p
                    break

            if path:
                path_obj = Path(path)
                filenames.append(path_obj.name)

        if filenames:
            combined = "\n".join(filenames)
            self.parent.root.clipboard_clear()
            self.parent.root.clipboard_append(combined)
        
            # 计算总行数
            total_lines = combined.count("\n") + 1
        
            # 使用带行数的状态消息
            self.parent.status_var.set(
                self.parent.texts.get("status_filenames_copied_with_lines", "已复制 {0} 个文件名 | 共 {1} 行").format(
                    len(filenames), total_lines
                )
            )
        else:
            self.parent.status_var.set(self.parent.texts["status_no_selection"])

    def _collect_files_recursively(
    self, dir_path, checked_only=True, parent_checked=True
):
        """递归收集目录中的所有文件"""
        all_files = []

        try:
            entries = list(dir_path.iterdir())
            
            # 应用与目录树相同的过滤规则
            # 1. 过滤隐藏文件
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
            
            # 2. 应用.gitignore过滤
            if self.parent.use_gitignore.get():
                # 查找项目根目录
                project_root = self.parent.dir_path.get().strip()
                project_root = normalize_path(project_root)
                
                # 筛选条目
                filtered_entries = []
                for e in entries:
                    if not is_ignored_by_gitignore(str(e), project_root):
                        filtered_entries.append(e)
                entries = filtered_entries
            
            # 3. 应用文件过滤器
            filter_pattern = self.parent.file_filter.get().strip()
            if filter_pattern:
                try:
                    pattern = re.compile(filter_pattern)
                    entries = [e for e in entries if pattern.search(e.name)]
                except re.error:
                    pass

            # 4. 应用文件/文件夹显示选项
            filtered_entries = []
            for entry in entries:
                if entry.is_dir() and self.parent.show_folders.get():
                    filtered_entries.append(entry)
                elif entry.is_file() and self.parent.show_files.get():
                    filtered_entries.append(entry)
            entries = filtered_entries
            
            # 处理过滤后的文件
            for item in entries:
                item_path_str = str(item)
                item_in_tree = item_path_str in self.parent.tree_items

                if item_in_tree:
                    item_id = self.parent.tree_items[item_path_str]
                    item_checked = item_id in self.parent.checked_items
                else:
                    item_checked = parent_checked

                if checked_only and not item_checked:
                    continue

                if item.is_file():
                    all_files.append(item)
                elif item.is_dir():
                    all_files.extend(
                        self._collect_files_recursively(
                            item, checked_only, item_checked
                        )
                    )
        except Exception as e:
            print(f"收集文件时出错: {str(e)}")
            pass

        return all_files

    def process_selected_files(self, content_processor=None):
        """通用文件处理函数，支持自定义内容处理器

        Args:
            content_processor: 接收path_obj并返回处理后内容的函数
                               如果为None，则仅收集路径

        Returns:
            处理结果的列表和处理文件数量
        """
        selected_items = self.parent.tree.selection()
        if not selected_items:
            return [], 0

        results = []
        processed_paths = set()

        for item in selected_items:
            if item not in self.parent.checked_items:
                continue

            path = None
            for p, tree_id in self.parent.tree_items.items():
                if tree_id == item:
                    path = p
                    break

            if not path:
                continue

            path_obj = Path(path)

            if path_obj.is_file():
                if str(path_obj) not in processed_paths:
                    processed_paths.add(str(path_obj))

                    if content_processor:
                        try:
                            if is_text_file(str(path_obj)):
                                result = content_processor(path_obj)
                                if result:
                                    results.append(result)
                        except Exception as e:
                            self.parent.status_var.set(f"处理文件出错: {str(e)}")
                    else:
                        # 仅添加路径
                        results.append(
                            self.format_path(self.get_relative_path(path_obj))
                        )

            elif path_obj.is_dir():
                all_files = self._collect_files_recursively(path_obj, True, True)
                for file in all_files:
                    if str(file) not in processed_paths:
                        processed_paths.add(str(file))

                        if content_processor:
                            try:
                                if is_text_file(str(file)):
                                    result = content_processor(file)
                                    if result:
                                        results.append(result)
                            except Exception:
                                # 跳过无法处理的文件
                                continue
                        else:
                            # 仅添加路径
                            results.append(
                                self.format_path(self.get_relative_path(file))
                            )

        return results, len(results)

    def save_to_file(self):
        """将目录树文本保存到文件"""
        text = self._get_tree_text()

        if not text:
            self.parent.status_var.set(self.parent.texts["status_no_selection"])
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )

        if file_path:
            try:
                Path(file_path).write_text(text, encoding="utf-8")
                self.parent.status_var.set(
                    self.parent.texts["status_saved_to"].format(file_path)
                )
            except Exception as e:
                self.parent.status_var.set(
                    self.parent.texts["status_save_failed"].format(str(e))
                )

    def get_relative_path(self, path):
        """获取相对于根目录的路径"""
        if self.parent.use_relative_path.get():
            root_dir = Path(normalize_path(self.parent.dir_path.get().strip()))
            path_obj = Path(normalize_path(str(path)))
            try:
                rel_path = path_obj.relative_to(root_dir)
                # 使用反斜杠
                return f"{root_dir.name}\\{rel_path}".replace("/", "\\")
            except ValueError:
                return str(path_obj).replace("/", "\\")
        else:
            return str(Path(path)).replace("/", "\\")

    def format_path(self, path):
        """使用设定的前缀和后缀格式化路径"""
        return f"{self.parent.PATH_PREFIX}{path}{self.parent.PATH_SUFFIX}"

    def format_code(self, code):
        """使用设定的前缀和后缀格式化代码"""
        return f"{self.parent.CODE_PREFIX}{code}{self.parent.CODE_SUFFIX}"
