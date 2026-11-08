# P1-A：读取授权和有界输出

涉及 `devpilot/devpilot/` 下：tools/repo/read_file.py、file_cache.py、streaming.py；Runner 删除预授权缓存路径。

缓存仅在 ReadFile 授权路径内使用；摘要分块读取，结果最多 500 行且受字节额度约束。超长单行分块丢弃尾部；读取/搜索返回截断标记，要求完整内容的补丁/进程捕获超限明确失败。

验证：test_denied_read_never_opens_content、test_cached_access_reauthorizes_and_changed_content_invalidates、test_long_line_and_unicode_result_are_bounded。

回退：按本单元职责撤回，保留已验证的权限修复；不删除运行目录或旧证据，不转换检查点版本。完整结果见 [交付记录](README.md)。
