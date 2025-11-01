// Database yerine kullanılacak sabit (dummy) gönderi verileri
const DUMMY_POSTS = [
    {
        id: 1,
        username: "FatihAk",
        content: "Nihayet o bağımlılık hatalarından kurtulduk! Bu statik siteyi yayınlamak çok daha kolay olacak. Artık sadece görünüm önemli.",
        timestamp: "2 dakika önce"
    },
    {
        id: 2,
        username: "Berke_Dev",
        content: "Flask ve Python ile uğraşmak yerine saf JS ile prototip oluşturmak hızlı bir çözümdür. Projenin genel mimarisini basitleştirdik.",
        timestamp: "1 saat önce"
    },
    {
        id: 3,
        username: "AppCloud_Bot",
        content: "Unutmayın: Gerçek kullanıcı yönetimi, veritabanı ve SocketIO için sunucu tarafı bir teknoloji (Node.js, Go, veya Python/Flask) gereklidir.",
        timestamp: "Dün"
    }
];

const postFeed = document.getElementById('post-feed');
const loadingMsg = document.getElementById('loading-msg');
const submitPostBtn = document.getElementById('submit-post-btn');

/**
 * Gönderi akışını statik verilerle doldurur
 */
function renderPosts() {
    loadingMsg.style.display = 'none'; // 'Yükleniyor' mesajını gizle

    DUMMY_POSTS.forEach(post => {
        const postElement = document.createElement('div');
        postElement.className = 'post';

        postElement.innerHTML = `
            <div class="post-header">
                <div class="avatar"></div>
                <span class="username">${post.username}</span>
            </div>
            <div class="post-content">
                <p>${post.content}</p>
            </div>
            <div class="post-footer">
                <span>Gönderilme: ${post.timestamp}</span>
            </div>
        `;
        postFeed.appendChild(postElement);
    });
}

/**
 * Yeni gönderi butonuna tıklanınca uyarı verir (kaydetmez)
 */
submitPostBtn.addEventListener('click', () => {
    const postContent = document.getElementById('post-input').value;
    if (postContent.trim() === "") {
        alert("Lütfen bir şeyler yazın!");
        return;
    }
    alert(`Gönderiniz alındı:\n"${postContent.substring(0, 50)}..."\n\nUYARI: Bu statik bir sitedir. Veriler sunucuya kaydedilmedi.`);
    document.getElementById('post-input').value = ''; // Alanı temizle
});


// Sayfa yüklendiğinde gönderileri render et
document.addEventListener('DOMContentLoaded', renderPosts);