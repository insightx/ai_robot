"""
设置管理模块

该模块负责加载、保存和管理应用程序设置，包括用户界面语言、
文件过滤规则、路径格式化方式等。支持从文件中加载设置和将设置保存到文件中。
"""

import json
from pathlib import Path
import os
import sys

from ai_code_context_helper.config import (
    DEFAULT_PATH_PREFIX,
    DEFAULT_PATH_SUFFIX,
    DEFAULT_CODE_PREFIX,
    DEFAULT_CODE_SUFFIX,
    MAX_HISTORY_ITEMS,
    SETTINGS_FILENAME,
)
from ai_code_context_helper.file_utils import normalize_path


class SettingsManager:
    """
    管理应用程序设置的类

    负责加载、保存和管理用户设置，包括界面语言、文件过滤器、路径格式等。
    使用JSON文件持久化存储设置，支持多语言界面。

    Attributes:
        settings_file (Path): 设置文件路径
        languages (dict): 支持的语言和文本字典
        PATH_PREFIX (str): 文件路径前缀
        PATH_SUFFIX (str): 文件路径后缀
        CODE_PREFIX (str): 代码前缀
        CODE_SUFFIX (str): 代码后缀
        show_hidden_value (bool): 是否显示隐藏文件
        show_files_value (bool): 是否显示文件
        show_folders_value (bool): 是否显示文件夹
        use_relative_path_value (bool): 是否使用相对路径
        max_depth_value (int): 目录树最大深度
        file_filter_value (str): 文件过滤器
        preserve_tree_state_value (bool): 是否保留树状态
        dir_history (list): 目录历史记录
        current_language (str): 当前语言代码
        texts (dict): 当前语言文本
        show_advanced_options_value (bool): 是否显示高级选项
        settings_changed (bool): 设置是否已更改
        max_history_items (int): 最大历史记录数量
    """

    def __init__(self, languages):
        """
        初始化设置管理器

        Args:
            languages (dict): 支持的语言和文本字典
        """
        script_dir = Path(os.path.dirname(os.path.abspath(sys.argv[0])))
        # 开发模式使用当前包目录
        if os.path.exists(os.path.join(script_dir, "resources")):
            self.settings_file = script_dir / "resources" / SETTINGS_FILENAME
        # 否则使用打包后的路径
        else:
            self.settings_file = script_dir / SETTINGS_FILENAME
        self.languages = languages

        # 默认设置
        self.PATH_PREFIX = DEFAULT_PATH_PREFIX
        self.PATH_SUFFIX = DEFAULT_PATH_SUFFIX
        self.CODE_PREFIX = DEFAULT_CODE_PREFIX
        self.CODE_SUFFIX = DEFAULT_CODE_SUFFIX
        self.show_hidden_value = False
        self.show_files_value = True
        self.show_folders_value = True
        self.use_relative_path_value = True
        self.max_depth_value = 0
        self.file_filter_value = ""
        self.dir_history = []
        self.current_language = "en_US"
        self.texts = self.languages.get(self.current_language, self.languages["en_US"])
        self.show_advanced_options_value = True
        self.enable_easy_multiselect_value = True
        self.expanded_states = {}
        self.use_gitignore_value = False
        self.is_topmost_value = False

        self.settings_changed = False
        self.max_history_items = MAX_HISTORY_ITEMS

        self.load_settings()

    def load_settings(self):
        """
        从配置文件加载应用程序设置

        读取JSON格式的设置文件，更新设置属性。
        如果设置文件不存在或无法读取，将使用默认设置。
        """
        try:
            if self.settings_file.exists():
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)

                    if "path_prefix" in settings:
                        self.PATH_PREFIX = settings["path_prefix"]
                    if "path_suffix" in settings:
                        self.PATH_SUFFIX = settings["path_suffix"]
                    if "code_prefix" in settings:
                        self.CODE_PREFIX = settings["code_prefix"]
                    if "code_suffix" in settings:
                        self.CODE_SUFFIX = settings["code_suffix"]

                    self.show_hidden_value = settings.get("show_hidden", False)
                    self.show_files_value = settings.get("show_files", True)
                    self.show_folders_value = settings.get("show_folders", True)
                    self.use_relative_path_value = settings.get(
                        "use_relative_path", True
                    )
                    self.max_depth_value = settings.get("max_depth", 0)
                    self.file_filter_value = settings.get("file_filter", "")
                    self.show_advanced_options_value = settings.get(
                        "show_advanced_options", True
                    )
                    self.enable_easy_multiselect_value = settings.get(
                        "enable_easy_multiselect", True
                    )
                    self.use_gitignore_value = settings.get("use_gitignore", False)
                    self.is_topmost_value = settings.get("is_topmost", False)

                    # 加载目录历史和展开状态
                    self.dir_history = []
                    self.expanded_states = {}

                    if "directory_history" in settings:
                        for entry in settings["directory_history"]:
                            if "path" in entry:
                                path = normalize_path(entry["path"])
                                self.dir_history.append(path)
                                if "expanded_paths" in entry:
                                    print(f"从设置加载展开状态: {path} -> {entry['expanded_paths']}")
                                    self.expanded_states[path] = entry["expanded_paths"]
                        
                        # 限制历史记录数量
                        if len(self.dir_history) > self.max_history_items:
                            self.dir_history = self.dir_history[:self.max_history_items]

                    # 加载语言设置
                    self.current_language = settings.get("language", "en_US")
                    if self.current_language not in self.languages:
                        self.current_language = "en_US"
                    self.texts = self.languages[self.current_language]

                    self.settings_changed = False
        except Exception as e:
            print(f"{self.texts['load_settings_failed'].format(e)}")

    def save_settings(self):
        """保存设置，使用原子写入"""
        if not self.settings_changed:
            return True
        
        try:
            # 验证并构建设置数据（现有逻辑保持不变）
            valid_history = [path for path in self.dir_history if path and os.path.exists(path)]
            if len(valid_history) != len(self.dir_history):
                self.dir_history = valid_history

            directory_history = []
            for path in self.dir_history:
                entry = {"path": path}
                if path in self.expanded_states:
                    entry["expanded_paths"] = self.expanded_states[path]
                directory_history.append(entry)

            settings = {
                "path_prefix": self.PATH_PREFIX,
                "path_suffix": self.PATH_SUFFIX,
                "code_prefix": self.CODE_PREFIX,
                "code_suffix": self.CODE_SUFFIX,
                "show_hidden": self.show_hidden_value,
                "show_files": self.show_files_value,
                "show_folders": self.show_folders_value,
                "use_relative_path": self.use_relative_path_value,
                "max_depth": self.max_depth_value,
                "file_filter": self.file_filter_value,
                "language": self.current_language,
                "directory_history": directory_history,
                "show_advanced_options": self.show_advanced_options_value,
                "enable_easy_multiselect": self.enable_easy_multiselect_value,
                "use_gitignore": self.use_gitignore_value,
                "is_topmost": self.is_topmost_value,
            }

            # 确保目录存在
            settings_dir = os.path.dirname(self.settings_file)
            os.makedirs(settings_dir, exist_ok=True)

            # 原子写入
            temp_file = str(self.settings_file) + '.tmp'
        
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
        
            # 原子替换
            if os.name == 'nt':
                if os.path.exists(self.settings_file):
                    os.replace(temp_file, self.settings_file)
                else:
                    os.rename(temp_file, self.settings_file)
            else:
                os.rename(temp_file, self.settings_file)

            self.settings_changed = False
            print(f"设置已保存")
            return True

        except Exception as e:
            # 清理临时文件
            temp_file = str(self.settings_file) + '.tmp'
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except:
                    pass
            print(f"保存设置失败: {str(e)}")
            return False

    def update_expanded_state(self, directory, expanded_paths):
        """
        更新目录的展开状态，合并现有状态和新状态

        Args:
            directory (str): 目录路径
            expanded_paths (list): 新的展开路径列表
        """
        directory = normalize_path(directory)

        if directory in self.expanded_states:
            # 合并现有和新的展开路径，保留所有路径
            existing_paths = self.expanded_states[directory]
            merged_paths = list(set(existing_paths + expanded_paths))
            self.expanded_states[directory] = merged_paths
        else:
            self.expanded_states[directory] = expanded_paths

        self.settings_changed = True
        self.save_settings()
