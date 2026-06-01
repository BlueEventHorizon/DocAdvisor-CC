import tempfile

# sandbox が TMPDIR をプロジェクトルートに書き換えるため、
# 一時ディレクトリをシステムデフォルト (/tmp) に固定する。
tempfile.tempdir = "/tmp"
