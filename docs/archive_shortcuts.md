# Archive Shortcuts

Before using either shortcut, edit the matching `.ps1` file and replace the
`<멘토선생님 작성글 목록 URL>` placeholder with the real mentor teacher article-list URL.

## One-Shot Archive Shortcut

1. Right-click the Windows desktop.
2. Select New -> Shortcut.
3. Use this target:

```text
powershell.exe -NoExit -ExecutionPolicy Bypass -File "C:\projects\naver_cafe_archive\scripts\run_archive_once.ps1"
```

4. Name the shortcut:

```text
Archive Run Once
```

## Market Schedule Loop Shortcut

1. Right-click the Windows desktop.
2. Select New -> Shortcut.
3. Use this target:

```text
powershell.exe -NoExit -ExecutionPolicy Bypass -File "C:\projects\naver_cafe_archive\scripts\start_archive_loop.ps1"
```

4. Name the shortcut:

```text
Archive Market Loop
```

The shortcuts only wrap the proven archive routine. They do not perform
automatic login or bypass CAPTCHA, identity verification, or Cafe permissions.
