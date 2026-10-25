"""
对话框模块

该模块负责处理各种对话框和弹窗，包括上下文菜单、格式设置对话框、
关于作者窗口等。提供用户与应用程序交互的辅助界面元素。
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from pathlib import Path
import webbrowser

from ai_code_context_helper.tooltip import create_tooltip
from ai_code_context_helper.file_utils import normalize_path
from ai_code_context_helper.config import (
    QRCODE_FILENAME,
    QRCODE_WINDOW_SIZE,
    FORMAT_WINDOW_SIZE,
    FORMAT_WINDOW_MIN_SIZE,
    RESOURCES_DIR,
    QRCODE_WINDOW_TITLE,
    QRCODE_TEXT,
    UI_FONT_FAMILY,
    CHANGELOG_URL,
)


class DialogManager:
    """
    管理对话框和弹窗的类

    负责创建和管理应用程序的各种对话框和弹窗，包括上下文菜单、历史记录菜单、
    格式设置对话框和关于作者界面等。

    Attributes:
        parent (CodeContextGenerator): 父对象，提供对主应用程序的访问

    Methods:
        show_context_menu(event): 显示右键上下文菜单
        show_dir_history_menu(event): 显示目录历史记录的右键菜单
        show_format_settings(): 显示文本格式设置对话框
        show_qrcode(): 显示公众号二维码图片
        open_changelog(): 打开更新日志页面
    """

    def __init__(self, parent):
        """
        初始化对话框管理器

        Args:
            parent (CodeContextGenerator): 父对象，提供对主应用程序的访问
        """
        self.parent = parent

    def show_context_menu(self, event):
        """
        显示右键上下文菜单

        在鼠标右键点击位置显示上下文菜单，提供文件和目录操作选项。
        根据所点击项目的类型（文件或目录）动态调整菜单内容。

        Args:
            event: 鼠标右键点击事件对象
        """
        item = self.parent.tree.identify_row(event.y)
        if not item:
            return

        if not self.parent.tree.selection():
            self.parent.tree.selection_set(item)
        elif item not in self.parent.tree.selection():
            self.parent.tree.selection_set(item)

        self.parent.context_menu.delete(0, tk.END)

        is_directory = False
        for path, tree_id in self.parent.tree_items.items():
            if tree_id == item and Path(path).is_dir():
                is_directory = True
                break

        if is_directory:
            # 检查是否只选择了一个目录
            if len(self.parent.tree.selection()) == 1:
                self.parent.context_menu.add_command(
                    label=self.parent.texts.get("open_folder", "在资源管理器中打开")
                    + " (Ctrl+F)",
                    command=self.parent.open_folder,
                )
                self.parent.context_menu.add_command(
                    label=self.parent.texts.get("open_terminal", "打开命令行")
                    + " (Ctrl+T)",
                    command=self.parent.open_terminal,
                )
                self.parent.context_menu.add_separator()

            self.parent.context_menu.add_command(
                label=self.parent.texts["expand_all"],
                command=self.parent.tree_ops.expand_all,
            )

        self.parent.context_menu.add_command(
            label=self.parent.texts["copy_path_and_code"] + " (Ctrl+C)",
            command=self.parent.clipboard_ops.copy_both,
        )
        self.parent.context_menu.add_command(
            label=self.parent.texts["copy_path"],
            command=self.parent.clipboard_ops.copy_path,
        )

        self.parent.context_menu.add_command(
            label=self.parent.texts["copy_code"],
            command=self.parent.clipboard_ops.copy_code,
        )
        self.parent.context_menu.add_command(
            label=self.parent.texts["copy_filename"] + " (Ctrl+B)",
            command=self.parent.clipboard_ops.copy_filename,
        )

        self.parent.context_menu.post(event.x_root, event.y_root)

    def show_dir_history_menu(self, event):
        """
        显示目录历史记录的右键菜单

        在历史记录下拉框中右键点击时显示菜单，提供删除单个历史记录
        或清空全部历史记录的选项。

        Args:
            event: 鼠标右键点击事件对象
        """
        history_menu = tk.Menu(self.parent.root, tearoff=0)

        current_dir = self.parent.dir_path.get().strip()
        current_dir = normalize_path(current_dir)

        # 显示所有历史路径项
        if self.parent.dir_history:
            for dir_path in self.parent.dir_history:
                history_menu.add_command(
                    label=self.parent.texts["remove_from_history"].format(dir_path),
                    command=lambda path=dir_path: self.parent.remove_from_history(path),
                )

            history_menu.add_separator()
            history_menu.add_command(
                label=self.parent.texts["clear_history"],
                command=self.parent.clear_all_history,
            )
        else:
            history_menu.add_command(
                label=self.parent.texts["no_history"], state="disabled"
            )

        history_menu.post(event.x_root, event.y_root)

    def show_format_settings(self):
        """
        显示文本格式设置对话框

        创建一个模态对话框，允许用户配置路径和代码的前缀后缀格式。
        提供保存和取消按钮，支持设置的即时预览。
        """
        format_window = tk.Toplevel(self.parent.root)
        format_window.title(self.parent.texts["format_settings"])
        format_window.geometry(FORMAT_WINDOW_SIZE)
        format_window.minsize(*FORMAT_WINDOW_MIN_SIZE)
        format_window.transient(self.parent.root)
        format_window.grab_set()

        self.parent.gui.center_window(format_window)

        frame = ttk.LabelFrame(
            format_window, text=self.parent.texts["format_settings"], padding="10"
        )
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        prefix_label = ttk.Label(frame, text=self.parent.texts["path_prefix"])
        prefix_label.grid(row=0, column=0, sticky=tk.W, pady=5)
        create_tooltip(prefix_label, self.parent.texts["tooltip_prefix_entry"])

        # 将实际换行符替换为可见的字符串表示
        display_path_prefix = self.parent.PATH_PREFIX.replace("\n", "\\n")
        path_prefix_var = tk.StringVar(value=display_path_prefix)
        prefix_entry = ttk.Entry(frame, textvariable=path_prefix_var, width=40)
        prefix_entry.grid(row=0, column=1, sticky=tk.W + tk.E, pady=5)
        create_tooltip(prefix_entry, self.parent.texts["tooltip_prefix_entry"])

        suffix_label = ttk.Label(frame, text=self.parent.texts["path_suffix"])
        suffix_label.grid(row=1, column=0, sticky=tk.W, pady=5)
        create_tooltip(suffix_label, self.parent.texts["tooltip_suffix_entry"])

        display_path_suffix = self.parent.PATH_SUFFIX.replace("\n", "\\n")
        path_suffix_var = tk.StringVar(value=display_path_suffix)
        suffix_entry = ttk.Entry(frame, textvariable=path_suffix_var, width=40)
        suffix_entry.grid(row=1, column=1, sticky=tk.W + tk.E, pady=5)
        create_tooltip(suffix_entry, self.parent.texts["tooltip_suffix_entry"])

        code_prefix_label = ttk.Label(frame, text=self.parent.texts["code_prefix"])
        code_prefix_label.grid(row=2, column=0, sticky=tk.W, pady=5)
        create_tooltip(code_prefix_label, self.parent.texts["tooltip_prefix_entry"])

        display_code_prefix = self.parent.CODE_PREFIX.replace("\n", "\\n")
        code_prefix_var = tk.StringVar(value=display_code_prefix)
        code_prefix_entry = ttk.Entry(frame, textvariable=code_prefix_var, width=40)
        code_prefix_entry.grid(row=2, column=1, sticky=tk.W + tk.E, pady=5)
        create_tooltip(code_prefix_entry, self.parent.texts["tooltip_prefix_entry"])

        code_suffix_label = ttk.Label(frame, text=self.parent.texts["code_suffix"])
        code_suffix_label.grid(row=3, column=0, sticky=tk.W, pady=5)
        create_tooltip(code_suffix_label, self.parent.texts["tooltip_suffix_entry"])

        display_code_suffix = self.parent.CODE_SUFFIX.replace("\n", "\\n")
        code_suffix_var = tk.StringVar(value=display_code_suffix)
        code_suffix_entry = ttk.Entry(frame, textvariable=code_suffix_var, width=40)
        code_suffix_entry.grid(row=3, column=1, sticky=tk.W + tk.E, pady=5)
        create_tooltip(code_suffix_entry, self.parent.texts["tooltip_suffix_entry"])

        # 添加自动换行功能，设置合适的宽度
        tip_label = ttk.Label(frame, text=self.parent.texts["note"], wraplength=450)
        tip_label.grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=10)

        btn_frame = ttk.Frame(format_window)
        btn_frame.pack(fill=tk.X, pady=10)

        def save_settings():
            """保存格式设置并更新应用程序设置"""
            self.parent.PATH_PREFIX = path_prefix_var.get().replace("\\n", "\n")
            self.parent.PATH_SUFFIX = path_suffix_var.get().replace("\\n", "\n")
            self.parent.CODE_PREFIX = code_prefix_var.get().replace("\\n", "\n")
            self.parent.CODE_SUFFIX = code_suffix_var.get().replace("\\n", "\n")

            # 更新设置管理器中的值
            self.parent.settings.PATH_PREFIX = self.parent.PATH_PREFIX
            self.parent.settings.PATH_SUFFIX = self.parent.PATH_SUFFIX
            self.parent.settings.CODE_PREFIX = self.parent.CODE_PREFIX
            self.parent.settings.CODE_SUFFIX = self.parent.CODE_SUFFIX
            self.parent.settings.settings_changed = True

            format_window.destroy()
            self.parent.status_var.set(self.parent.texts["format_text_updated"])

        save_btn = ttk.Button(
            btn_frame, text=self.parent.texts["save"], command=save_settings
        )
        save_btn.pack(side=tk.RIGHT, padx=5)
        create_tooltip(save_btn, self.parent.texts["tooltip_save_btn"])

        cancel_btn = ttk.Button(
            btn_frame, text=self.parent.texts["cancel"], command=format_window.destroy
        )
        cancel_btn.pack(side=tk.RIGHT, padx=5)
        create_tooltip(cancel_btn, self.parent.texts["tooltip_cancel_btn"])

    def show_qrcode(self):
        """
        显示公众号二维码图片

        创建一个模态窗口显示作者公众号二维码，支持用户关注和获取更新。
        """
        qrcode_window = tk.Toplevel(self.parent.root)
        qrcode_window.title(QRCODE_WINDOW_TITLE)
        qrcode_window.transient(self.parent.root)
        qrcode_window.grab_set()

        qrcode_window.geometry(QRCODE_WINDOW_SIZE)
        self.parent.gui.center_window(qrcode_window)

        # 创建一个框架来容纳图片和按钮
        frame = ttk.Frame(qrcode_window)
        frame.pack(fill=tk.BOTH, expand=True)

        # 使用配置常量
        qrcode_path = Path(__file__).parent / RESOURCES_DIR / QRCODE_FILENAME

        try:
            img = Image.open(qrcode_path)
            img = img.resize((500, 182), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)

            img_label = ttk.Label(frame, image=photo)
            img_label.image = photo  # 保持引用防止被垃圾回收
            img_label.pack(pady=10)

            text_label = ttk.Label(frame, text=QRCODE_TEXT, font=(UI_FONT_FAMILY, 10))
            text_label.pack(pady=5)

        except Exception as e:
            error_label = ttk.Label(
                frame, text=f"无法加载图片: {str(e)}", foreground="red"
            )
            error_label.pack(pady=20)

    def open_changelog(self):
        """
        打开更新日志页面

        在默认浏览器中打开项目更新日志的GitHub页面。
        """
        webbrowser.open(CHANGELOG_URL)
