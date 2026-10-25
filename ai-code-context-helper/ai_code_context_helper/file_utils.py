"""
文件工具模块

提供文件操作相关的工具函数，包括路径标准化、文本文件检测、
内容读取和编码处理等。支持智能检测文本文件的编码，特别对中文编码
提供了增强支持。

Functions:
    normalize_path(path): 将路径标准化为Windows风格
    is_text_file(file_path): 检测文件是否为文本文件
    read_file_content(path_obj): 智能读取文件内容，自动处理编码
"""

import os
import re
from pathlib import Path
from charset_normalizer import from_path, is_binary
from ai_code_context_helper.config import (
    MAX_TEXT_FILE_SIZE,
    CHINESE_ENCODINGS,
    PREVIEW_CHARS_LENGTH,
)

_gitignore_cache = {}


def _should_refresh_cache(gitignore_path):
    """检查是否需要刷新缓存"""
    if not os.path.exists(gitignore_path):
        return True

    try:
        current_mtime = os.path.getmtime(gitignore_path)
        if gitignore_path in _gitignore_cache:
            cached_mtime, _ = _gitignore_cache[gitignore_path]
            return current_mtime != cached_mtime
        return True
    except OSError:
        return True


def _parse_gitignore(gitignore_path):
    """解析.gitignore文件，带简化的缓存机制"""
    if not os.path.exists(gitignore_path):
        return []

    # 检查是否需要刷新缓存
    if not _should_refresh_cache(gitignore_path):
        _, rules = _gitignore_cache[gitignore_path]
        return rules

    print(f"重新解析 .gitignore 文件: {gitignore_path}")

    rules = []
    try:
        current_mtime = os.path.getmtime(gitignore_path)

        with open(gitignore_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.rstrip("\n\r")
                if not line or line.lstrip().startswith("#"):
                    continue
                if line.endswith(" ") and not line.endswith("\\ "):
                    line = line.rstrip(" ")
                line = line.replace("\\ ", " ")
                is_negation = line.startswith("!")
                try:
                    pattern = _glob_to_regex(line)
                    rules.append((pattern, is_negation, line))
                except Exception as e:
                    print(f"Error parsing {gitignore_path} line {line_num}: {e}")

        _gitignore_cache[gitignore_path] = (current_mtime, rules)
        print(f"已缓存 .gitignore 规则: {len(rules)} 条规则")

    except Exception as e:
        print(f"Error reading {gitignore_path}: {e}")

    return rules


def clear_gitignore_cache():
    """清除所有.gitignore缓存"""
    global _gitignore_cache
    old_count = len(_gitignore_cache)
    _gitignore_cache = {}
    print(f"已清除 {old_count} 个.gitignore缓存项")


def force_refresh_gitignore():
    """强制刷新所有.gitignore缓存（通过清除缓存实现）"""
    clear_gitignore_cache()
    print("已强制刷新所有 .gitignore 缓存")


def _glob_to_regex(pattern):
    """
    将gitignore模式转换为正则表达式
    完全符合Git的.gitignore语法规则
    """
    original = pattern
    regex_parts = []
    i = 0

    # 检查是否是否定规则（以!开头）
    is_negation = pattern.startswith("!")
    if is_negation:
        pattern = pattern[1:]

    # 检查是否以斜杠开头（绝对路径）
    is_absolute = pattern.startswith("/")
    if is_absolute:
        pattern = pattern[1:]
        regex_parts.append("^")
    else:
        # 相对路径可以匹配任何位置
        regex_parts.append("(^|.*/)")

    # 检查是否以斜杠结尾（只匹配目录）
    is_dir_only = pattern.endswith("/")
    if is_dir_only:
        pattern = pattern[:-1]

    # 处理模式中的每个字符
    while i < len(pattern):
        c = pattern[i]

        if c == "*":
            # 检查是否是 ** 模式
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                # ** 匹配任意数量的目录
                if i + 2 < len(pattern) and pattern[i + 2] == "/":
                    # **/something 模式
                    regex_parts.append("(.*/)?")
                    i += 3  # 跳过 **/
                    continue
                elif i == len(pattern) - 2:
                    # something/** 模式
                    regex_parts.append("(/.*)?")
                    i += 2
                    continue
                else:
                    # 单独的 ** 被视为无效，当作两个 *
                    regex_parts.append("[^/]*[^/]*")
                    i += 2
                    continue
            else:
                # 单个 * 匹配除了斜杠之外的任意字符
                regex_parts.append("[^/]*")
                i += 1

        elif c == "?":
            # ? 匹配单个字符（除了斜杠）
            regex_parts.append("[^/]")
            i += 1

        elif c == "[":
            # 字符集合 [abc] 或 [a-z]
            j = i + 1
            if j < len(pattern) and pattern[j] == "!":
                # [!...] 表示否定字符集
                j += 1
            if j < len(pattern) and pattern[j] == "]":
                # 第一个字符是 ]，它是集合的一部分
                j += 1

            # 找到配对的 ]
            while j < len(pattern) and pattern[j] != "]":
                j += 1

            if j >= len(pattern):
                # 没有找到配对的 ]，将 [ 当作普通字符
                regex_parts.append(re.escape(c))
                i += 1
            else:
                # 找到了完整的字符集合
                char_set = pattern[i : j + 1]
                # 转换字符集合，确保不匹配斜杠
                if char_set.startswith("[!"):
                    # 否定集合 [!...] -> [^...]
                    inner = char_set[2:-1]
                    if "/" not in inner:
                        inner += "/"
                    regex_parts.append(f"[^{re.escape(inner)}]")
                else:
                    # 普通集合 [...]
                    inner = char_set[1:-1]
                    # 确保不包含斜杠
                    inner = inner.replace("/", "")
                    regex_parts.append(f"[{re.escape(inner)}]")
                i = j + 1

        elif c == "\\":
            # 转义字符
            if i + 1 < len(pattern):
                # 转义下一个字符
                regex_parts.append(re.escape(pattern[i + 1]))
                i += 2
            else:
                # 尾部的反斜杠
                regex_parts.append(re.escape(c))
                i += 1

        elif c == ".":
            # . 在regex中有特殊含义，需要转义
            regex_parts.append(re.escape(c))
            i += 1

        elif c in "^$+{}|()":
            # 其他regex特殊字符需要转义
            regex_parts.append(re.escape(c))
            i += 1

        else:
            # 普通字符
            regex_parts.append(re.escape(c))
            i += 1

    # 构建最终的正则表达式
    regex = "".join(regex_parts)

    # 处理目录匹配
    if is_dir_only:
        # 只匹配目录（以/结尾或者是最后一个路径组件）
        regex += "(/|$)"
    else:
        # 可以匹配文件或目录
        regex += "(/.*)?$"

    # 编译正则表达式
    # Windows文件系统不区分大小写
    flags = re.IGNORECASE if os.name == "nt" else 0

    try:
        compiled = re.compile(regex, flags)
        return compiled
    except re.error as e:
        print(f"Error compiling regex for pattern '{original}': {e}")
        print(f"Generated regex: {regex}")
        # 返回一个永远不匹配的正则表达式
        return re.compile("(?!.*)", flags)


def is_ignored_by_gitignore(path, root_dir):
    """
    检查路径是否被.gitignore忽略，完全符合Git的规则

    Args:
        path: 要检查的路径（绝对路径）
        root_dir: 项目根目录（绝对路径）

    Returns:
        bool: 如果路径被忽略则返回True，否则返回False
    """
    # 标准化路径
    path = os.path.normpath(path)
    root_dir = os.path.normpath(root_dir)

    # .gitignore文件本身不被忽略
    if os.path.basename(path) == ".gitignore":
        return False

    # 获取相对路径
    try:
        rel_path = os.path.relpath(path, root_dir)
    except ValueError:
        # 路径不在root_dir内
        return False

    # Windows路径转换为Unix风格（Git使用Unix风格路径）
    rel_path = rel_path.replace(os.sep, "/")

    # 如果是当前目录，不忽略
    if rel_path == ".":
        return False

    # 检查是否是目录
    is_directory = os.path.isdir(path)

    # 初始化忽略状态
    ignored = False

    # 收集所有相关的.gitignore文件（从根目录到当前文件的父目录）
    gitignore_files = []
    rel_dir = os.path.dirname(rel_path)

    # 添加根目录的.gitignore
    root_gitignore = os.path.join(root_dir, ".gitignore")
    if os.path.exists(root_gitignore):
        gitignore_files.append((root_gitignore, ""))

    # 逐级添加子目录的.gitignore
    if rel_dir and rel_dir != ".":
        path_parts = rel_dir.split("/")
        for i in range(len(path_parts)):
            sub_path = "/".join(path_parts[: i + 1])
            sub_dir = os.path.join(root_dir, sub_path.replace("/", os.sep))
            sub_gitignore = os.path.join(sub_dir, ".gitignore")
            if os.path.exists(sub_gitignore):
                gitignore_files.append((sub_gitignore, sub_path))

    # 按照Git的规则处理每个.gitignore文件
    for gitignore_path, gitignore_rel_dir in gitignore_files:
        rules = _parse_gitignore(gitignore_path)

        # 计算相对于当前.gitignore文件的路径
        if gitignore_rel_dir:
            if rel_path.startswith(gitignore_rel_dir + "/"):
                check_path = rel_path[len(gitignore_rel_dir) + 1 :]
            else:
                continue
        else:
            check_path = rel_path

        # 对于目录，在检查时也要尝试加上尾部斜杠
        paths_to_check = [check_path]
        if is_directory:
            paths_to_check.append(check_path + "/")

        # 应用规则
        for pattern, is_negation, original_rule in rules:
            for p in paths_to_check:
                if pattern.match(p):
                    ignored = not is_negation
                    break

    return ignored


def normalize_path(path):
    """将路径中的正斜杠转换为反斜杠，统一使用Windows风格路径"""
    if path:
        return path.replace("/", "\\")
    return path


def is_text_file(file_path):
    """检测文件是否为文本文件，使用charset-normalizer判断"""
    path = Path(file_path)

    # 检查文件大小
    try:
        file_size = path.stat().st_size
        if file_size > MAX_TEXT_FILE_SIZE:  # 超过10MB就不处理
            return False
        if file_size == 0:  # 空文件视为文本文件
            return True
    except Exception:
        return False

    try:
        with open(str(path), "rb") as f:
            content = f.read()
            # 如果是二进制文件，返回False
            if is_binary(content):
                return False
            # 使用from_path尝试检测编码，如果有结果则是文本文件
            matches = from_path(str(path))
            return len(matches) > 0
    except Exception:
        return False

    # 默认返回False
    return False


def get_file_stats(file_path):
    """
    获取文件统计信息（行数和大小）

    Args:
        file_path: 文件路径

    Returns:
        tuple: (行数, 文件大小(字节), 文件大小的格式化字符串)
    """
    path = Path(file_path)
    try:
        # 获取文件大小
        size_bytes = path.stat().st_size

        # 格式化文件大小
        if size_bytes < 1024:
            size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            size_str = f"{size_bytes/1024:.1f} KB"
        else:
            size_str = f"{size_bytes/(1024*1024):.1f} MB"

        # 获取文件行数
        if is_text_file(file_path):
            try:
                with open(file_path, "rb") as f:
                    line_count = sum(1 for _ in f)
            except Exception:
                line_count = 0
        else:
            line_count = 0

        return line_count, size_bytes, size_str
    except Exception as e:
        print(f"获取文件统计信息失败: {str(e)}")
        return 0, 0, "0 B"


def read_file_content(path_obj):
    """智能读取文件内容，使用多种方法尝试检测正确的编码"""
    try:
        # 如果文件不存在或大小为0，返回空字符串
        if not path_obj.exists() or path_obj.stat().st_size == 0:
            return ""

        # 先检查是否为文本文件
        if not is_text_file(path_obj):
            raise Exception("文件不是文本文件")

        # 使用charset_normalizer检测可能的编码并遍历所有匹配项
        matches = from_path(str(path_obj))

        # 尝试所有中文常见编码（如果检测到中文）
        best_match = matches.best()
        if best_match and best_match.language == "Chinese":
            for encoding in CHINESE_ENCODINGS:
                try:
                    with open(str(path_obj), "r", encoding=encoding) as f:
                        content = f.read()
                        # 检查是否有乱码特征
                        if (
                            not "\ufffd" in content[:PREVIEW_CHARS_LENGTH]
                        ):  # 检查前1000个字符中是否有替换字符
                            return content
                except UnicodeDecodeError:
                    continue

        # 返回最可能匹配的结果
        if len(matches) > 0:
            return str(matches.best())

        return open(str(path_obj), "r", encoding="utf-8", errors="replace").read()

    except Exception as e:
        raise Exception(f"无法读取文件: {str(e)}")
