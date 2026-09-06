let currentPath = "";

function loadDirectory(path) {
  const statusMsg = document.getElementById('status-message');
  if (statusMsg) statusMsg.textContent = "Yükleniyor...";
  
  // URL'den PIN geçişi kaldırıldı, sadece secure session cookie ile çalışır (Faz 8.2)
  fetch(`/api/v1/files/list?root=downloads&path=${encodeURIComponent(path)}`)
    .then(r => r.json())
    .then(data => {
      if(data.error) { 
        alert("Hata: " + data.message); 
        if (statusMsg) statusMsg.textContent = "Hata oluştu.";
        return; 
      }
      currentPath = path;
      document.getElementById('current-path').textContent = "/" + path;
      if (statusMsg) statusMsg.textContent = "Dizin yüklendi: /" + path;
      renderList(data.entries);
    })
    .catch(err => {
      console.error(err);
      if (statusMsg) statusMsg.textContent = "Bağlantı hatası.";
    });
}

function renderList(entries) {
  const container = document.getElementById('file-list');
  container.innerHTML = '';
  
  entries.sort((a, b) => b.is_dir - a.is_dir || a.name.localeCompare(b.name));
  
  for(const entry of entries) {
    const div = document.createElement('div');
    div.className = 'file-item';
    div.setAttribute("role", "listitem");
    
    // WCAG: Gerçek button/a kullanımı, span yerine semantic etkileşim
    const actionBtn = document.createElement('button');
    actionBtn.className = 'file-name';
    actionBtn.textContent = (entry.is_dir ? "📁 " : "📄 ") + entry.name;
    
    if (entry.is_dir) {
      actionBtn.setAttribute("aria-label", entry.name + " klasörünü aç");
      actionBtn.onclick = () => loadDirectory(currentPath ? currentPath + "/" + entry.name : entry.name);
    } else {
      actionBtn.setAttribute("aria-label", entry.name + " dosyasını indir");
      actionBtn.onclick = () => {
        const dlPath = currentPath ? currentPath + "/" + entry.name : entry.name;
        window.location.href = `/api/v1/files/download?root=downloads&path=${encodeURIComponent(dlPath)}`;
      };
    }
    
    const sizeSpan = document.createElement('span');
    sizeSpan.className = 'file-size';
    sizeSpan.textContent = entry.is_dir ? "-" : (entry.size / 1024).toFixed(1) + " KB";
    
    div.appendChild(actionBtn);
    div.appendChild(sizeSpan);
    container.appendChild(div);
  }
}

document.getElementById('btn-up').onclick = () => {
  if (!currentPath) return;
  const parts = currentPath.split('/');
  parts.pop();
  loadDirectory(parts.join('/'));
};

// Dosya yükleme: ham bayt gövde + ?name= (sunucu multipart beklemez).
document.getElementById('btn-upload').onclick = () => {
  const input = document.getElementById('upload-input');
  const bar = document.getElementById('upload-progress');
  const msg = document.getElementById('upload-status');
  if (!input.files || input.files.length === 0) {
    msg.textContent = "Önce dosya seçin.";
    return;
  }
  const file = input.files[0];
  if (file.size === 0 || file.size > 100 * 1024 * 1024) {
    msg.textContent = "Dosya 1 bayt–100 MB aralığında olmalı.";
    return;
  }
  bar.hidden = false;
  bar.value = 0;
  msg.textContent = "Yükleniyor: " + file.name;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/v1/files/upload?name=' + encodeURIComponent(file.name));
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) bar.value = Math.round(e.loaded * 100 / e.total);
  };
  xhr.onload = () => {
    bar.value = 100;
    try {
      const data = JSON.parse(xhr.responseText);
      if (xhr.status === 200 && data.status === 'ok') {
        msg.textContent = "Yüklendi: " + file.name + " (" + data.bytes + " bayt)";
        input.value = "";
        loadDirectory(currentPath);
      } else {
        msg.textContent = "Hata: " + (data.error || xhr.status);
      }
    } catch (err) {
      msg.textContent = "Sunucu yanıtı okunamadı.";
    }
  };
  xhr.onerror = () => { msg.textContent = "Bağlantı hatası."; };
  xhr.send(file);
};

// İlk yükleme
loadDirectory("");
