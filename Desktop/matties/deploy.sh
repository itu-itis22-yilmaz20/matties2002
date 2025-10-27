#!/bin/bash
# ===========================
#  Otomatik GitHub Yükleme
#  Kemal Berke Yılmaz - Matties
# ===========================

# 1️⃣ Değişiklikleri al
git add .

# 2️⃣ Commit mesajı oluştur
echo "Commit mesajı yaz (boş bırakılırsa tarih eklenecek):"
read msg
if [ -z "$msg" ]; then
    msg="Otomatik yükleme: $(date '+%Y-%m-%d %H:%M:%S')"
fi

# 3️⃣ Commit et
git commit -m "$msg"

# 4️⃣ Ana dalı ayarla (gerekirse)
git branch -M main

# 5️⃣ Uzak depo ekli değilse (ilk kez kullanıyorsan)
if ! git remote | grep -q origin; then
    echo "GitHub repo bağlantısını gir (örnek: https://github.com/berkeyilmaz/matties.git):"
    read repo
    git remote add origin "$repo"
fi

# 6️⃣ GitHub’a gönder
git push -u origin main

echo "✅ Yükleme tamamlandı!"
