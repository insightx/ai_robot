"""
工具提示模块

该模块提供工具提示（tooltip）功能，用于在用户将鼠标悬停在控件上时
显示辅助信息，提高用户界面的易用性和可理解性。
"""

import tkinter as tk
from tkinter import ttk

from ai_code_context_helper.config import (
    UI_TOOLTIP_FONT,
    UI_TOOLTIP_BG_COLOR,
    UI_TOOLTIP_DELAY,
)


class ToolTip:
    """
    创建一个提示框，在用户将鼠标悬停在控件上时显示帮助文本

    提供用户友好的工具提示功能，当用户将鼠标悬停在控件上时显示解释性文本。
    支持显示延迟、自动位置计算和样式自定义。

    Attributes:
        widget (tk.Widget): 提示将附加到的控件
        text (str): 要显示的提示文本
        tip_window (tk.Toplevel): 提示窗口实例
        id (int): 计时器ID，用于延迟显示
    """

    def __init__(self, widget, text):
        """
        初始化工具提示

        Args:
            widget (tk.Widget): 提示将附加到的控件
            text (str): 要显示的提示文本
        """
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, event=None):
        """
        当鼠标进入控件时，安排显示提示

        Args:
            event: 鼠标进入事件对象
        """
        self.schedule()

    def leave(self, event=None):
        """
        当鼠标离开控件或按下按钮时，取消安排并隐藏提示

        Args:
            event: 鼠标离开或按下事件对象
        """
        self.unschedule()
        self.hide()

    def schedule(self):
        """安排提示在指定延迟后显示"""
        self.unschedule()
        self.id = self.widget.after(UI_TOOLTIP_DELAY, self.show)

    def unschedule(self):
        """取消之前安排的显示"""
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def show(self):
        """显示提示窗口，位置在控件下方"""
        if self.tip_window:
            return

        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background=UI_TOOLTIP_BG_COLOR,
            relief=tk.SOLID,
            borderwidth=1,
            font=UI_TOOLTIP_FONT,
        )
        label.pack(ipadx=5, ipady=3)

    def hide(self):
        """隐藏并销毁提示窗口"""
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


def create_tooltip(widget, text):
    """
    为控件创建工具提示的便捷函数

    Args:
        widget (tk.Widget): 需要添加提示的控件
        text (str): 提示文本

    Returns:
        ToolTip: 创建的工具提示对象
    """
    return ToolTip(widget, text)
