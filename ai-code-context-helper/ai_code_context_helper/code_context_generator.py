"""
代码上下文生成器主模块

该模块包含应用程序的主类 CodeContextGenerator，负责协调其他所有模块，
管理应用程序的核心业务逻辑，处理用户输入和事件响应。
它提供了生成代码上下文、复制文件路径和代码内容等核心功能。

Classes:
    CodeContextGenerator: 应用程序的主类，协调所有功能模块
"""

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, ttk
import pystray
from PIL import Image, ImageDraw
from pynput import keyboard
import threading
import platform

from ai_code_context_helper.file_utils import (
    normalize_path,
)
from ai_code_context_helper.settings_manager import SettingsManager
from ai_code_context_helper.languages import LANGUAGES
from ai_code_context_helper import __version__

from ai_code_context_helper.gui_components import GUIComponents
from ai_code_context_helper.tree_operations import TreeOperations
from ai_code_context_helper.clipboard_operations import ClipboardOperations
from ai_code_context_helper.dialogs import DialogManager
from ai_code_context_helper.config import (
    UI_FONT_FAMILY,
    UI_BUTTON_FONT_SIZE,
    UI_LABEL_FONT_SIZE,
    UI_TREEVIEW_FONT_SIZE,
    UI_HEADING_FONT_SIZE,
    UI_HEADING_FONT_STYLE,
    DEFAULT_WINDOW_SIZE,
    DEFAULT_WINDOW_MIN_SIZE,
    RESOURCES_DIR,
    ICON_FILENAME,
)


class CodeContextGenerator:
    """代码上下文生成器应用程序主类"""

    def __init__(self, root):
        self.root = root
    
        # 先隐藏窗口，避免在配置过程中显示
        self.root.withdraw()

        self.languages = LANGUAGES
        # 初始化设置管理器
        self.settings = SettingsManager(LANGUAGES)
        # 跟踪高级选项的显示状态
        self.show_advanced_options = self.settings.show_advanced_options_value

        # 添加窗口置顶状态变量
        self.is_topmost = tk.BooleanVar(value=self.settings.is_topmost_value)

        # 从设置中获取当前语言和文本
        self.current_language = self.settings.current_language
        self.texts = self.settings.texts

        self.version = __version__

        self.root.title(f"{self.texts['app_title']} v{self.version}")
    
        # 设置窗口大小但不设置位置
        self.root.geometry("800x600")
        self.root.minsize(600, 400)

        # 根据初始设置立即应用窗口置顶状态
        if self.is_topmost.get():
            self.root.wm_attributes("-topmost", 1)

        # 使用设置管理器中的值
        self.PATH_PREFIX = self.settings.PATH_PREFIX
        self.PATH_SUFFIX = self.settings.PATH_SUFFIX
        self.CODE_PREFIX = self.settings.CODE_PREFIX
        self.CODE_SUFFIX = self.settings.CODE_SUFFIX
        self.dir_history = self.settings.dir_history

        self.tree_items = {}
        self.checked_items = set()

        self.context_menu = tk.Menu(root, tearoff=0)

        self.style = ttk.Style()
        self.style.configure("TButton", font=(UI_FONT_FAMILY, UI_BUTTON_FONT_SIZE))
        self.style.configure("TCheckbutton", font=(UI_FONT_FAMILY, UI_LABEL_FONT_SIZE))
        self.style.configure("TLabel", font=(UI_FONT_FAMILY, UI_LABEL_FONT_SIZE))
        self.style.configure("Treeview", font=(UI_FONT_FAMILY, UI_TREEVIEW_FONT_SIZE))
        self.style.configure(
            "Treeview.Heading",
            font=(UI_FONT_FAMILY, UI_HEADING_FONT_SIZE, UI_HEADING_FONT_STYLE),
        )

        # 重新设置窗口大小（如果DEFAULT_WINDOW_SIZE不同的话）
        self.root.geometry(DEFAULT_WINDOW_SIZE)
        self.root.minsize(*DEFAULT_WINDOW_MIN_SIZE)

        # 初始化各个模块
        self.gui = GUIComponents(self)
        self.tree_ops = TreeOperations(self)
        self.clipboard_ops = ClipboardOperations(self)
        self.dialog_mgr = DialogManager(self)

        # 创建GUI组件
        self.gui.create_widgets()

        self.root.bind(
            "<Control-c>", lambda event: self._handle_shortcut(event, self.copy_both)
        )
        self.root.bind(
            "<Control-b>",
            lambda event: self._handle_shortcut(event, self.copy_filename),
        )
        self.root.bind(
            "<Control-f>", lambda event: self._handle_shortcut(event, self.open_folder)
        )
        self.root.bind(
            "<Control-t>",
            lambda event: self._handle_shortcut(event, self.open_terminal),
        )

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
    
        # 先居中窗口，然后显示 - 修改这里
        self.gui.center_window(self.root)
        self.root.deiconify()  # 显示窗口

        self._initial_loading = True
        self._current_loaded_directory = None

        self._setup_initial_directory()
        self.root.after(100, self._setup_tree_bindings)

        self.root.after(100, self._setup_tree_bindings)

        try:
            icon_path = Path(__file__).parent / RESOURCES_DIR / ICON_FILENAME
            self.root.iconbitmap(str(icon_path))
        except Exception as e:
            print(f"无法加载图标: {str(e)}")
        
        # 初始化系统托盘图标
        self._create_system_tray()

        # 注册全局快捷键Ctrl+2
        self._register_global_hotkey()

        self._setup_auto_save()

    def _setup_auto_save(self):
        """设置自动保存机制 - 每30秒保存所有设置"""
        self._auto_save_interval = 30000  # 30秒
        self._schedule_auto_save()

    def _schedule_auto_save(self):
        """安排下一次自动保存"""
        if hasattr(self, "root") and self.root.winfo_exists():
            self.root.after(self._auto_save_interval, self._auto_save_task)

    def _auto_save_task(self):
        """执行自动保存任务"""
        try:
            if self.settings.settings_changed:
                print("执行自动保存...")
                self.settings.save_settings()
        except Exception as e:
            print(f"自动保存出错: {str(e)}")
        finally:
            self._schedule_auto_save()

    def _setup_initial_directory(self):
        """设置初始目录并安排加载"""
        if self.dir_history and len(self.dir_history) > 0:
            # 查找第一个有效的目录
            for dir_path in self.dir_history:
                if dir_path and Path(dir_path).is_dir():
                    print(f"找到有效的历史目录: {dir_path}")
                    self.dir_path.set(dir_path)
                    # 延迟生成树，确保界面初始化完成
                    self.root.after(300, self._initial_tree_load)
                    return

            # 如果所有历史目录都无效
            print("所有历史目录都无效，清空历史")
            self.dir_history = []
            self.dir_entry["values"] = []
            self.settings.dir_history = []
            self.settings.settings_changed = True
            self._initial_loading = False
        else:
            print("没有历史目录记录")
            self._initial_loading = False

    def _handle_shortcut(self, event, callback_function):
        """通用快捷键处理函数，根据当前焦点决定行为

        Args:
            event: 触发的事件对象
            callback_function: 当焦点不在输入控件上时要调用的函数

        Returns:
            如果拦截了事件，返回"break"，否则返回None
        """
        # 获取当前具有焦点的小部件
        focused_widget = self.root.focus_get()

        # 检查焦点是否在输入框类控件上
        if isinstance(focused_widget, (ttk.Entry, ttk.Combobox, tk.Entry, tk.Text)):
            # 在输入框上，使用默认的行为
            return

        # 焦点不在输入框上，执行应用程序的特定功能
        callback_function()
        return "break"  # 阻止事件继续传播

    def open_folder(self):
        """在资源管理器中打开选中的文件夹"""
        # 获取选中的项目
        selected_items = self.tree.selection()
        if len(selected_items) != 1:
            self.status_var.set(
                self.texts.get("status_select_single_folder", "请选择单个文件夹")
            )
            return

        item_id = selected_items[0]
        # 查找对应的路径
        for path, tree_id in self.tree_items.items():
            if tree_id == item_id and Path(path).is_dir():
                try:
                    import subprocess
                    import os

                    # 在Windows上使用explorer打开文件夹
                    if os.name == "nt":
                        subprocess.Popen(f'explorer "{path}"')
                    # 在macOS上使用open命令
                    elif os.name == "posix" and os.uname().sysname == "Darwin":
                        subprocess.Popen(["open", path])
                    # 在Linux上尝试使用xdg-open
                    elif os.name == "posix":
                        subprocess.Popen(["xdg-open", path])

                    self.status_var.set(
                        self.texts.get(
                            "status_folder_opened", "已打开文件夹: {0}"
                        ).format(path)
                    )
                    return
                except Exception as e:
                    self.status_var.set(f"打开文件夹失败: {str(e)}")
                    return

        self.status_var.set(self.texts.get("status_select_folder", "请选择一个文件夹"))

    def open_terminal(self):
        """在选中的文件夹中打开命令行"""
        # 获取选中的项目
        selected_items = self.tree.selection()
        if len(selected_items) != 1:
            self.status_var.set(
                self.texts.get("status_select_single_folder", "请选择单个文件夹")
            )
            return

        item_id = selected_items[0]
        # 查找对应的路径
        for path, tree_id in self.tree_items.items():
            if tree_id == item_id and Path(path).is_dir():
                try:
                    import subprocess
                    import os

                    # 在Windows上使用cmd打开命令行
                    if os.name == "nt":
                        subprocess.Popen(f'start cmd /K "cd /d "{path}""', shell=True)
                    # 在macOS上使用Terminal应用
                    elif os.name == "posix" and os.uname().sysname == "Darwin":
                        subprocess.Popen(["open", "-a", "Terminal", path])
                    # 在Linux上尝试使用默认终端
                    elif os.name == "posix":
                        try:
                            # 尝试使用xdg-terminal-exec (较新的发行版)
                            subprocess.Popen(
                                ["xdg-terminal-exec", "--working-directory", path]
                            )
                        except FileNotFoundError:
                            # 回退到一些常见的终端模拟器
                            for terminal in [
                                "gnome-terminal",
                                "konsole",
                                "xfce4-terminal",
                                "xterm",
                            ]:
                                try:
                                    if terminal == "gnome-terminal":
                                        subprocess.Popen(
                                            [terminal, "--working-directory", path]
                                        )
                                    else:
                                        subprocess.Popen([terminal, "--workdir", path])
                                    break
                                except FileNotFoundError:
                                    continue

                    self.status_var.set(
                        self.texts.get(
                            "status_terminal_opened", "已在 {0} 打开命令行"
                        ).format(path)
                    )
                    return
                except Exception as e:
                    self.status_var.set(f"打开命令行失败: {str(e)}")
                    return

        self.status_var.set(self.texts.get("status_select_folder", "请选择一个文件夹"))

    def _initial_tree_load(self):
        """初始化时加载目录树并应用保存的展开状态，不保存当前状态"""
        directory = self.dir_path.get().strip()

        # 检查目录是否有效
        if not directory or not Path(directory).is_dir():
            print("初始化加载: 目录无效或为空")
            self._initial_loading = False  # 标记初始化完成，即使失败了
            return False

        print(f"===== 初始化加载目录: {directory} =====")
        # 设置当前加载的目录
        self._current_loaded_directory = directory
        # 生成树时应用保存的状态，但不触发保存
        self.tree_ops.generate_tree(preserve_state=True)
        self._initial_loading = False  # 标记初始化完成
        return True

    def _setup_tree_bindings(self):
        """设置树视图的自定义绑定"""
        # 首先解除所有可能冲突的默认绑定
        self.tree.unbind("<Double-1>")
        self.tree.unbind("<<TreeviewOpen>>")

        # 然后绑定到我们的自定义处理函数
        self.tree.bind("<Double-1>", self.tree_ops.on_tree_double_click)
        self.tree.bind("<<TreeviewOpen>>", self.tree_ops.on_tree_open, add="+")

        # 添加一个辅助绑定，在展开图标点击后立即触发内容加载
        self.tree.bind("<Button-1>", self._on_tree_button_click, add="+")

    def _on_tree_button_click(self, event):
        """辅助函数处理树点击事件"""
        region = self.tree.identify_region(event.x, event.y)
        if region == "tree":  # 点击在展开/折叠图标上
            item_id = self.tree.identify_row(event.y)
            if item_id:
                # 在点击后短暂延迟，让TreeviewOpen事件先处理
                self.root.after(100, lambda: self._check_load_children(item_id))

    def _check_load_children(self, item_id):
        """检查并确保节点的子内容被加载"""
        # 如果节点处于展开状态，确保其子内容已加载
        if self.tree.item(item_id, "open"):
            path = None
            for p, tree_id in self.tree_items.items():
                if tree_id == item_id:
                    path = p
                    break

            if path and Path(path).is_dir():
                # 使用tree_ops的方法加载内容
                self.tree_ops._load_children_content(item_id, path)

    def on_close(self):
        """窗口关闭时的处理函数，保存设置并销毁窗口"""
        print("应用程序关闭，保存最终状态")
        # 保存当前展开状态
        self._save_expanded_state()
        # 强制保存设置
        self.settings.settings_changed = True
        self.settings.save_settings()
        self.root.destroy()

    def toggle_topmost(self):
        """切换窗口置顶状态"""
        current_state = self.is_topmost.get()
        # 切换状态
        new_state = not current_state
        self.is_topmost.set(new_state)

        # 设置窗口置顶属性
        self.root.wm_attributes("-topmost", 1 if new_state else 0)

        # 更新状态栏消息
        if new_state:
            self.status_var.set(self.texts.get("status_topmost_enabled", "窗口已置顶"))
        else:
            self.status_var.set(
                self.texts.get("status_topmost_disabled", "窗口已取消置顶")
            )

        # 保存设置
        self.settings.is_topmost_value = new_state
        self.settings.settings_changed = True
        self.settings.save_settings()

    def reset_tree(self):
        """重置目录树，只保留根节点展开"""
        print("===== 重置目录树 =====")
        directory = self.dir_path.get().strip()
        if directory and Path(directory).is_dir():
            # 标准化路径
            directory = normalize_path(directory)
            # 将展开状态重置为只有根目录
            self.settings.expanded_states[directory] = ["."]
            self.settings.settings_changed = True
            # 生成树时不保留状态
            self.tree_ops.generate_tree(preserve_state=False)
            self.status_var.set(self.texts["status_tree_reset"])

    def update_tree(self):
        """更新目录树，保留当前展开状态"""
        print("===== 更新目录树 =====")
        directory = self.dir_path.get().strip()
        if directory and Path(directory).is_dir():
            # 更新目录树时强制刷新 .gitignore 缓存
            from ai_code_context_helper.file_utils import clear_gitignore_cache

            clear_gitignore_cache()
            # 先保存当前的滚动位置
            try:
                # 获取当前可见区域的开始和结束位置
                scroll_position = self.tree.yview()
                first_visible_fraction = scroll_position[0]

                # 尝试标识当前可见的第一个项目
                visible_items = []
                for item in self.tree.get_children():
                    if self.tree.exists(item):  # 确保项目存在
                        item_y = self.tree.bbox(item)
                        if item_y and item_y[1] >= 0:  # y坐标大于等于0表示可见
                            visible_items.append(item)
                            if len(visible_items) >= 3:  # 获取前3个可见项即可
                                break

                # 保存第一个可见项的文本和父项文本，用于后续匹配
                first_visible_info = []
                for item in visible_items:
                    item_text = self.tree.item(item, "text")
                    parent_id = self.tree.parent(item)
                    parent_text = ""
                    if parent_id:
                        parent_text = self.tree.item(parent_id, "text")
                    first_visible_info.append((item_text, parent_text))
            except Exception as e:
                print(f"保存滚动位置时出错: {str(e)}")
                first_visible_fraction = 0
                first_visible_info = []

            # 先保存当前的勾选状态
            current_checked_states = {}

            # 为每个路径记录其勾选状态
            for path, item_id in self.tree_items.items():
                is_checked = item_id in self.checked_items
                current_checked_states[path] = is_checked

            # 保存当前展开状态
            self._save_expanded_state()

            # 生成树时保留状态
            self.tree_ops.generate_tree(preserve_state=True)

            # 恢复勾选状态
            new_checked_items = set()
            for path, item_id in self.tree_items.items():
                # 如果路径在之前的记录中，并且是勾选的
                if path in current_checked_states and current_checked_states[path]:
                    new_checked_items.add(item_id)
                # 如果路径在之前的记录中，并且是取消勾选的
                elif (
                    path in current_checked_states and not current_checked_states[path]
                ):
                    self.tree.item(item_id, values=("",))
                    self.tree.item(item_id, tags=("gray",))

            # 更新勾选项集合
            self.checked_items = new_checked_items

            # 尝试恢复滚动位置
            self.root.update_idletasks()  # 确保UI已更新

            try:
                # 策略1: 尝试基于文本和父项找到相似的可见项
                if first_visible_info:
                    found_match = False
                    for item_text, parent_text in first_visible_info:
                        matching_items = []
                        for item_id in self.tree.get_children():
                            if (
                                self.tree.exists(item_id)
                                and self.tree.item(item_id, "text") == item_text
                            ):
                                p_id = self.tree.parent(item_id)
                                if p_id and self.tree.item(p_id, "text") == parent_text:
                                    matching_items.append(item_id)
                                    found_match = True
                                    break

                        if matching_items:
                            # 使项目可见并根据原始位置调整
                            self.tree.see(matching_items[0])
                            # 微调回原来的相对位置
                            self.tree.yview_moveto(
                                max(0, first_visible_fraction - 0.01)
                            )
                            found_match = True
                            break

                    # 如果找不到匹配项，尝试直接使用存储的分数位置
                    if not found_match:
                        self.tree.yview_moveto(first_visible_fraction)
                else:
                    # 没有保存项信息，使用存储的分数位置
                    self.tree.yview_moveto(first_visible_fraction)
            except Exception as e:
                print(f"恢复滚动位置时出错: {str(e)}")
                # 出错时不做额外处理，使用默认滚动位置

            self.status_var.set(self.texts["status_tree_updated"])

    def _save_expanded_state(self):
        """立即保存展开状态"""
        current_dir = self.dir_path.get().strip()
        if not current_dir or not Path(current_dir).is_dir():
            return

        current_dir = normalize_path(current_dir)
        expanded_items = []

        def collect_expanded_items(parent=""):
            for item_id in self.tree.get_children(parent):
                is_open = self.tree.item(item_id, "open")
                item_path = None
                for path, tree_id in self.tree_items.items():
                    if tree_id == item_id:
                        item_path = path
                        break

                if item_path and is_open and Path(item_path).is_dir():
                    try:
                        rel_path = str(Path(item_path).relative_to(Path(current_dir)))
                        if rel_path == ".":
                            expanded_items.append(".")
                        else:
                            expanded_items.append(rel_path)
                        collect_expanded_items(item_id)
                    except (ValueError, TypeError):
                        pass

        collect_expanded_items()

        if "." not in expanded_items:
            expanded_items.append(".")

        self.settings.expanded_states[current_dir] = expanded_items
        self.settings.settings_changed = True

        # 立即保存关键状态
        self.settings.save_settings()

    def change_language(self, *args):
        """更改界面语言"""
        selected_display_name = self.language_var.get()
        selected_language = self.language_names.get(selected_display_name)

        if selected_language and selected_language != self.current_language:
            self.current_language = selected_language
            self.texts = LANGUAGES[self.current_language]
            self.settings.current_language = self.current_language
            self.settings.texts = self.texts
            self.settings.settings_changed = True
            self.gui.update_ui_texts()

            print("语言已更改，正在更新系统托盘菜单...")
            self._create_system_tray()

    def on_setting_option_changed(self, *args):
        """当设置选项改变时的处理函数"""
        self.settings.show_hidden_value = self.show_hidden.get()
        self.settings.show_files_value = self.show_files.get()
        self.settings.show_folders_value = self.show_folders.get()
        self.settings.use_relative_path_value = self.use_relative_path.get()
        self.settings.max_depth_value = self.max_depth.get()
        self.settings.file_filter_value = self.file_filter.get()
        self.settings.enable_easy_multiselect_value = self.enable_easy_multiselect.get()
        self.settings.use_gitignore_value = self.use_gitignore.get()
        self.settings.settings_changed = True

        directory = self.dir_path.get().strip()
        if directory and Path(directory).is_dir():
            # 如果是gitignore相关设置变更，强制刷新缓存
            if args and self.settings.settings_changed:
                from ai_code_context_helper.file_utils import clear_gitignore_cache

                clear_gitignore_cache()

            self.tree_ops.generate_tree(preserve_state=True)

    def on_dir_changed(self, *args):
        """当目录路径改变时的处理函数"""
        print(f"===== on_dir_changed 被触发 =====")

        # 如果是初始化加载，不保存当前状态
        if hasattr(self, "_initial_loading") and self._initial_loading:
            print("初始化阶段，跳过处理")
            return

        # 获取新目录
        new_directory = self.dir_path.get().strip()
        print(f"新目录: {new_directory}")

        # 检查目录是否存在
        if new_directory and not Path(new_directory).is_dir():
            print(f"目录不存在: {new_directory}")

            # 如果目录不存在且在历史记录中，则删除它
            if new_directory in self.dir_history:
                self.remove_from_history(new_directory)

            # 清空目录树
            self.tree.delete(*self.tree.get_children())
            self.tree_items = {}
            self.checked_items = set()

            # 重置当前加载的目录
            self._current_loaded_directory = None

            # 更新状态栏
            self.status_var.set(self.texts["error_invalid_dir"])
            return

        if not new_directory:
            print("无效目录，跳过处理")
            return

        # 检查当前加载的目录
        current_dir = getattr(self, "_current_loaded_directory", None)
        print(f"当前已加载的目录: {current_dir}")

        # 如果是不同的目录，保存旧目录状态
        if current_dir and current_dir != new_directory and Path(current_dir).is_dir():
            print(f"保存旧目录 {current_dir} 的状态")
            # 临时将路径设置为旧目录以正确保存状态
            self.dir_path.set(current_dir)
            self._save_expanded_state()
            # 恢复新目录路径
            self.dir_path.set(new_directory)

        # 更新当前目录记录并加载新目录
        self._current_loaded_directory = new_directory
        print(f"设置当前目录为: {new_directory}")

        # 添加到历史并生成树
        self.add_to_history(new_directory)

        # 检查当前树的状态，如果为空或当前目录与上次不同，强制生成树
        should_generate = (
            len(self.tree.get_children()) == 0 or current_dir != new_directory
        )

        if should_generate:
            print(f"生成新目录树: {new_directory}")
            self.tree_ops.generate_tree(preserve_state=True)
        else:
            print(f"当前已显示目录 {new_directory} 的树，无需重新生成")

    def on_combobox_select(self, event):
        """当从Combobox中选择一个历史路径时的处理函数"""
        print(f"===== Combobox选择事件被触发 =====")
        selected_directory = self.dir_path.get().strip()
        print(f"从Combobox选择的目录: {selected_directory}")

        # 检查目录是否存在
        if selected_directory and not Path(selected_directory).is_dir():
            print(f"所选目录不存在: {selected_directory}")
            # 不清空目录地址栏，只清空目录树和显示错误信息
            self.tree.delete(*self.tree.get_children())
            self.tree_items = {}
            self.checked_items = set()
            self._current_loaded_directory = None
            self.status_var.set(self.texts["error_invalid_dir"])

            # 从历史记录中删除无效目录
            if selected_directory in self.dir_history:
                self.remove_from_history(selected_directory)
            return

        # 确保选择后触发目录变更处理，同时强制生成树
        # 先重置当前加载目录，确保会触发树的重新生成
        if self._current_loaded_directory != selected_directory:
            old_current = self._current_loaded_directory
            self._current_loaded_directory = None
            print(f"强制从 {old_current} 切换到 {selected_directory}")

        # 触发目录变更处理
        self.on_dir_changed()

        # 确保目录树已生成
        if len(self.tree.get_children()) == 0:
            print("Combobox选择后目录树为空，强制生成")
            self.tree_ops.generate_tree(preserve_state=True)

    def add_to_history(self, directory):
        """将目录添加到历史记录中"""
        if not directory:
            return

        # 标准化路径格式为Windows风格
        directory = normalize_path(directory)
        print(f"添加到历史记录: {directory}")

        # 如果目录已在历史记录中，先移除它，然后将其添加到开头
        if directory in self.dir_history:
            self.dir_history.remove(directory)

        self.dir_history.insert(0, directory)

        if len(self.dir_history) > self.settings.max_history_items:
            # 如果超出最大历史数量，移除多余项
            removed_paths = self.dir_history[self.settings.max_history_items :]
            self.dir_history = self.dir_history[: self.settings.max_history_items]

            # 清理不再需要的展开状态
            for path in removed_paths:
                if path in self.settings.expanded_states:
                    del self.settings.expanded_states[path]

        self.dir_entry["values"] = self.dir_history
        self.settings.dir_history = self.dir_history
        self.settings.settings_changed = True

    def remove_from_history(self, directory):
        """从历史记录中删除指定的目录"""
        if directory in self.dir_history:
            self.dir_history.remove(directory)

            # 同时删除对应的展开状态
            if directory in self.settings.expanded_states:
                del self.settings.expanded_states[directory]

            self.dir_entry["values"] = self.dir_history
            self.settings.dir_history = self.dir_history
            self.settings.settings_changed = True
            self.status_var.set(self.texts["status_history_removed"].format(directory))

            # 检查是否正在删除当前显示的目录
            current_dir = self.dir_path.get().strip()
            if current_dir == directory:
                print(f"删除当前显示的目录: {directory}")
                # 清空目录树
                self.tree.delete(*self.tree.get_children())
                self.tree_items = {}
                self.checked_items = set()

                # 保持目录地址栏内容不变，只重置内部追踪变量
                self._current_loaded_directory = None

    def clear_all_history(self):
        """清空所有目录历史记录"""
        self.dir_history = []
        self.dir_entry["values"] = []

        # 同时清空展开状态
        self.settings.expanded_states = {}

        self.settings.dir_history = self.dir_history
        self.settings.settings_changed = True
        self.status_var.set(self.texts["status_history_cleared"])

        # 清空当前目录视图
        self.tree.delete(*self.tree.get_children())
        self.tree_items = {}
        self.checked_items = set()

        # 清空目录地址栏
        self.dir_path.set("")
        self._current_loaded_directory = None

        # 重置初始化标记，以便能够重新加载新目录
        self._initial_loading = False

    def browse_directory(self):
        """打开文件夹选择对话框，允许用户浏览并选择目录"""
        # 保存当前目录状态在选择前，与on_dir_changed逻辑一致
        old_directory = self._current_loaded_directory
        if old_directory and Path(old_directory).is_dir():
            # 确保保存的是当前目录的状态
            temp = self.dir_path.get()
            self.dir_path.set(old_directory)
            self._save_expanded_state()
            self.dir_path.set(temp)

        directory = filedialog.askdirectory()
        if directory:
            # 检查目录是否存在
            if not Path(directory).is_dir():
                self.status_var.set(self.texts["error_invalid_dir"])
                return

            # 标准化为Windows风格路径
            directory = normalize_path(directory)
            self.dir_path.set(directory)

    def toggle_advanced_options(self):
        """切换高级选项的显示状态"""
        # 保留这个方法，因为它是核心功能
        self.show_advanced_options = not self.show_advanced_options

        # 更新设置
        self.settings.show_advanced_options_value = self.show_advanced_options
        self.settings.settings_changed = True

        if self.show_advanced_options:
            self.advanced_options_frame.pack(fill=tk.X, pady=5)
            self.toggle_btn.configure(text=self.texts["hide_options"])
            self.status_var.set(self.texts["status_options_shown"])
        else:
            self.advanced_options_frame.pack_forget()
            self.toggle_btn.configure(text=self.texts["show_options"])
            self.status_var.set(self.texts["status_options_hidden"])

    # 添加委托方法，将方法调用转发到对应模块
    def generate_tree(self):
        return self.tree_ops.generate_tree()

    def copy_to_clipboard(self):
        return self.clipboard_ops.copy_to_clipboard()

    def copy_path(self):
        return self.clipboard_ops.copy_path()

    def copy_code(self):
        return self.clipboard_ops.copy_code()

    def copy_both(self):
        return self.clipboard_ops.copy_both()

    def copy_filename(self):
        return self.clipboard_ops.copy_filename()

    def show_format_settings(self):
        return self.dialog_mgr.show_format_settings()

    def show_qrcode(self):
        return self.dialog_mgr.show_qrcode()

    def open_changelog(self):
        return self.dialog_mgr.open_changelog()

    def show_context_menu(self, event):
        return self.dialog_mgr.show_context_menu(event)

    def show_dir_history_menu(self, event):
        return self.dialog_mgr.show_dir_history_menu(event)

    def save_to_file(self):
        return self.clipboard_ops.save_to_file()

    def _create_system_tray(self):
        """创建系统托盘图标及相关菜单"""
        # 如果已存在托盘图标，先停止它
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                self.tray_icon.stop()
                print("已停止现有系统托盘图标")
            except Exception as e:
                print(f"停止现有托盘图标时出错: {e}")

        icon_path = Path(__file__).parent / RESOURCES_DIR / ICON_FILENAME
        if icon_path and icon_path.exists():
            try:
                # 使用现有图标
                icon = Image.open(str(icon_path))
            except:
                # 如果打开失败，使用默认图标
                icon = self._create_default_icon()
        else:
            icon = self._create_default_icon()

        # 创建菜单项 - 将显示窗口设为默认操作
        menu_items = [
            pystray.MenuItem(
                self.texts.get("tray_show", "显示主窗口"),
                self._show_window,
                default=True,
            ),  # 设为默认项，这样单击时会触发此操作
            pystray.MenuItem(
                self.texts.get("tray_hide", "隐藏主窗口"), self._hide_window
            ),
            pystray.MenuItem(self.texts.get("tray_exit", "退出"), self._exit_app),
        ]

        # 创建托盘图标
        self.tray_icon = pystray.Icon(
            "AI代码上下文助手",
            icon,
            self.texts.get("tray_title", "AI代码上下文助手"),
            menu=pystray.Menu(*menu_items),
        )

        # 设置左键单击动作
        self.tray_icon.on_activate = self._show_window

        # 在单独的线程中运行系统托盘
        threading.Thread(target=self._run_tray_icon, daemon=True).start()
        print("系统托盘已启动，单击图标将显示主窗口")

        # 重要：确保窗口关闭事件始终绑定到_on_close_to_tray方法
        # 这样点击窗口关闭按钮时只会隐藏窗口而不会退出应用
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)

    def _run_tray_icon(self):
        """在单独的线程中运行托盘图标"""
        try:
            self.tray_icon.run()
        except Exception as e:
            print(f"托盘图标运行出错: {e}")

    def _create_default_icon(self, size=64):
        """创建一个简单的默认图标"""
        image = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
        dc = ImageDraw.Draw(image)

        dc.rectangle(
            [(8, 8), (size - 8, size - 8)],
            fill=(45, 156, 219),
            outline=(28, 99, 139),
            width=2,
        )
        dc.text((size // 2 - 10, size // 2 - 10), "AI", fill=(255, 255, 255))

        return image

    def _show_window(self):
        """显示主窗口"""
        print("正在显示主窗口...")

        try:
            # 检查窗口是否存在
            if not self.root.winfo_exists():
                print("窗口不存在，无法显示")
                return

            # 取消窗口的最小化状态
            if platform.system() == "Windows":
                self.root.state("normal")

            # 恢复窗口
            self.root.deiconify()

            # 提升窗口到前台
            self.root.lift()

            # 强制获取焦点
            self.root.focus_force()

            # 确保窗口可见并正确绘制
            self.root.update()

            # 更新状态栏
            self.status_var.set(self.texts.get("status_window_shown", "已显示主窗口"))
            print("主窗口已成功显示")
        except Exception as e:
            print(f"显示窗口时出错: {e}")

    def _hide_window(self):
        """隐藏主窗口"""
        try:
            self._save_expanded_state()
            self.root.withdraw()

            # 更新状态栏
            self.status_var.set(self.texts.get("status_window_hidden", "主窗口已隐藏"))
            print("窗口已隐藏")
        except Exception as e:
            print(f"隐藏窗口时出错: {e}")

    def _on_close_to_tray(self):
        """窗口关闭时隐藏到托盘"""
        print("窗口关闭，隐藏到托盘")
        self._save_expanded_state()  # 保存展开状态
        self.root.withdraw()  # 隐藏窗口

        # 更新状态栏文本（虽然此时不可见）
        self.status_var.set(self.texts.get("status_window_hidden", "主窗口已隐藏"))

    def _exit_app(self):
        """完全退出应用程序"""
        print("从托盘退出应用程序")
        # 保存当前展开状态
        self._save_expanded_state()
        # 强制保存设置
        self.settings.settings_changed = True
        self.settings.save_settings()

        # 停止全局热键监听
        if hasattr(self, "hotkey_listener") and self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
                print("已停止全局热键监听")
            except Exception as e:
                print(f"停止热键监听时出错: {e}")

        # 停止托盘图标
        if hasattr(self, "tray_icon") and self.tray_icon:
            try:
                # 检查图标是否在运行
                if hasattr(self.tray_icon, "_running") and self.tray_icon._running:
                    self.tray_icon.stop()
                    print("已停止系统托盘图标")
            except Exception as e:
                print(f"停止托盘图标时出错: {e}")

        # 销毁主窗口
        self.root.destroy()

    def _register_global_hotkey(self):
        """注册全局快捷键Ctrl+2，切换主窗口显示/隐藏状态"""
        try:
            # 创建热键监听器
            self.hotkey_listener = keyboard.GlobalHotKeys(
                {"<ctrl>+2": self._on_hotkey_triggered}
            )
            # 启动监听线程
            self.hotkey_listener.start()
            print("全局快捷键Ctrl+2已注册，可按下该组合键切换主窗口显示/隐藏状态")
        except Exception as e:
            print(f"注册全局快捷键时出错: {e}")
            # 如果注册失败，设置为None以避免后续尝试关闭
            self.hotkey_listener = None

    def _on_hotkey_triggered(self):
        """全局快捷键触发时的处理函数，实现切换显示/隐藏功能"""
        print("全局快捷键Ctrl+2被触发，正在切换窗口状态")

        # 使用after方法确保在主线程中执行窗口状态切换操作
        self.root.after(0, self._toggle_window_visibility)

    def _toggle_window_visibility(self):
        """切换窗口的可见性状态"""
        try:
            # 检查窗口是否存在
            if not self.root.winfo_exists():
                print("窗口不存在，无法切换状态")
                return

            # 检查窗口当前状态
            # 注意：winfo_viewable()在窗口被withdraw到系统托盘时返回0
            # 如果窗口被最小化但未withdraw，仍返回1
            if self.root.winfo_viewable():
                print("窗口当前可见，正在隐藏到系统托盘")
                self._hide_window()
            else:
                print("窗口当前隐藏，正在显示")
                self._show_window()
        except Exception as e:
            print(f"切换窗口可见性时出错: {e}")
