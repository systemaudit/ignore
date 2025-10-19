#!/bin/bash
# ===========================================
# Setup & Upload Folder ~/abc ke GitHub
# User: systemaudit
# Repo: abc
# Token diambil dari environment variable $GITHUB_TOKEN
# ===========================================

GITHUB_USER="systemaudit"
REPO_NAME="abc"
LOCAL_DIR="$HOME/abc"
BRANCH="main"

# Pastikan token tersedia
if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ ERROR: Variabel lingkungan GITHUB_TOKEN belum diset."
  echo "Silakan jalankan: export GITHUB_TOKEN=<token_anda>"
  exit 1
fi

# Pastikan folder ada
if [ ! -d "$LOCAL_DIR" ]; then
  echo "❌ Folder $LOCAL_DIR tidak ditemukan!"
  exit 1
fi

cd "$LOCAL_DIR" || exit 1

# Inisialisasi git baru jika belum ada
if [ ! -d ".git" ]; then
  echo "📦 Inisialisasi repository git baru..."
  git init
  git branch -M $BRANCH
  git remote add origin https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git
else
  git remote set-url origin https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git
fi

# Tambahkan file dan commit
echo "🧾 Menambahkan file ke git..."
git add .

COMMIT_MSG="Initial upload from VPS on $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" || echo "⚠️ Tidak ada perubahan baru."

# Push ke GitHub
echo "🚀 Mengunggah ke GitHub..."
git push -u origin $BRANCH

# Cek hasil
if [ $? -eq 0 ]; then
  echo "✅ Selesai! Semua file telah diunggah ke:"
  echo "👉 https://github.com/$GITHUB_USER/$REPO_NAME"
else
  echo "❌ Gagal mengunggah. Periksa token atau izin GitHub."
fi
