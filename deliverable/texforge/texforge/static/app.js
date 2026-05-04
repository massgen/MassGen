const setTheme = () => {
  const saved = localStorage.getItem('texforge-theme');
  if (saved === 'light') document.body.classList.add('light');
};
setTheme();
document.getElementById('themeToggle')?.addEventListener('click', () => {
  document.body.classList.toggle('light');
  localStorage.setItem('texforge-theme', document.body.classList.contains('light') ? 'light' : 'dark');
});

const page = document.body.dataset.page;

if (page === 'dashboard') {
  const form = document.getElementById('projectForm');
  const status = document.getElementById('projectFormStatus');
  const registerForm = document.getElementById('registerForm');
  const loginForm = document.getElementById('loginForm');
  const authStatus = document.getElementById('authStatus');
  const templateSearchForm = document.getElementById('templateSearchForm');
  const templateSearchInput = document.getElementById('templateSearchInput');
  const templatePreview = document.getElementById('templatePreview');

  const renderTemplates = (templates) => {
    document.querySelectorAll('.template-card').forEach((card) => {
      const visible = templates.some((tpl) => tpl.slug === card.dataset.templateSlug);
      card.style.display = visible ? '' : 'none';
    });
  };

  document.querySelectorAll('.template-preview-button').forEach((button) => {
    button.addEventListener('click', async () => {
      const response = await fetch(`/api/templates/${button.dataset.templateSlug}`);
      const template = await response.json();
      templatePreview.textContent = `${template.name}\n\nmain.tex\n---------\n${template.main_tex}\n\nrefs.bib\n--------\n${template.refs_bib || '(empty)'}`;
    });
  });

  templateSearchForm?.addEventListener('submit', (event) => event.preventDefault());
  templateSearchInput?.addEventListener('input', async () => {
    const response = await fetch(`/api/templates?q=${encodeURIComponent(templateSearchInput.value)}`);
    const data = await response.json();
    renderTemplates(data.results);
  });
  form?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(form).entries());
    const response = await fetch('/api/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    status.textContent = `Created ${data.name}. Redirecting...`;
    window.location.href = `/projects/${data.id}`;
  });

  registerForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(registerForm).entries());
    const response = await fetch('/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    authStatus.textContent = response.ok ? 'Registered. You can now log in.' : 'Registration failed.';
  });

  loginForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(loginForm).entries());
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    authStatus.textContent = response.ok ? 'Logged in. Refreshing workspace...' : 'Login failed.';
    if (response.ok) window.location.reload();
  });
}

if (page === 'project') {
  const project = window.__PROJECT__;
  const projectId = document.body.dataset.projectId;
  const editor = document.getElementById('editor');
  const fileList = document.getElementById('fileList');
  const compileButton = document.getElementById('compileButton');
  const compileLog = document.getElementById('compileLog');
  const pdfFrame = document.getElementById('pdfFrame');
  const highlightPanel = document.getElementById('highlightPanel');
  const presenceStatus = document.getElementById('presenceStatus');
  const lintStatus = document.getElementById('lintStatus');
  const snapshotButton = document.getElementById('snapshotButton');
  const commentForm = document.getElementById('commentForm');
  const commentList = document.getElementById('commentList');
  const fileForm = document.getElementById('fileForm');
  const renameFileButton = document.getElementById('renameFileButton');
  const deleteFileButton = document.getElementById('deleteFileButton');
  const aiForm = document.getElementById('aiForm');
  const aiOutput = document.getElementById('aiOutput');
  const snapshotList = document.getElementById('snapshotList');
  const engineSelect = document.getElementById('engineSelect');
  const shareForm = document.getElementById('shareForm');
  const shareStatus = document.getElementById('shareStatus');
  const referenceForm = document.getElementById('referenceForm');
  const referenceList = document.getElementById('referenceList');
  const suggestionForm = document.getElementById('suggestionForm');
  const suggestionStatus = document.getElementById('suggestionStatus');
  const branchForm = document.getElementById('branchForm');
  const branchList = document.getElementById('branchList');
  const branchSnapshotSelect = document.getElementById('branchSnapshotSelect');
  let fileItems = [...document.querySelectorAll('.file-item')];
  let activeFile = project.files[0];
  let debounce;

  const renderHighlight = (content) => {
    highlightPanel.textContent = content;
    const begins = (content.match(/\\begin\{/g) || []).length;
    const ends = (content.match(/\\end\{/g) || []).length;
    lintStatus.textContent = begins === ends ? 'Lint: environments balanced' : 'Lint: check missing \\end{...}';
  };

  const selectFile = (item) => {
    fileItems.forEach((node) => node.classList.remove('active'));
    item.classList.add('active');
    activeFile = { id: item.dataset.fileId, path: item.dataset.filePath, content: item.dataset.fileContent };
    editor.value = activeFile.content;
    renderHighlight(activeFile.content);
  };

  if (fileItems.length) selectFile(fileItems[0]);
  fileItems.forEach((item) => item.addEventListener('click', () => selectFile(item)));

  const attachFileItem = (li) => {
    li.addEventListener('click', () => selectFile(li));
  };

  const refreshComments = async () => {
    const response = await fetch(`/api/projects/${projectId}/comments`);
    if (!response.ok) return;
    const data = await response.json();
    commentList.innerHTML = '';
    data.results.forEach((comment) => {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${comment.author}</strong> — ${comment.body} ${comment.resolved ? '<span class="badge">Resolved</span>' : ''}`;
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'ghost inline-action';
      toggle.textContent = comment.resolved ? 'Unresolve' : 'Resolve';
      toggle.addEventListener('click', async () => {
        await fetch(`/api/projects/${projectId}/comments/${comment.id}/${comment.resolved ? 'unresolve' : 'resolve'}`, { method: 'POST' });
        refreshComments();
      });
      li.appendChild(toggle);
      if (comment.replies?.length) {
        const replies = document.createElement('ul');
        replies.className = 'mini-list nested-list';
        comment.replies.forEach((reply) => {
          const replyItem = document.createElement('li');
          replyItem.innerHTML = `<strong>${reply.author}</strong> — ${reply.body}`;
          replies.appendChild(replyItem);
        });
        li.appendChild(replies);
      }
      commentList.appendChild(li);
    });
  };

  const addSnapshotOption = (snapshot) => {
    const li = document.createElement('li');
    li.dataset.snapshotId = snapshot.id;
    li.textContent = `${snapshot.name} — ${snapshot.created_at}`;
    snapshotList.prepend(li);

    const option = document.createElement('option');
    option.value = snapshot.id;
    option.textContent = snapshot.name;
    branchSnapshotSelect?.prepend(option);
    if (branchSnapshotSelect) branchSnapshotSelect.value = snapshot.id;
  };

  const refreshBranches = async () => {
    const response = await fetch(`/api/projects/${projectId}/branches`);
    if (!response.ok) return;
    const data = await response.json();
    branchList.innerHTML = '';
    data.results.forEach((branch) => {
      const li = document.createElement('li');
      li.innerHTML = `<strong>${branch.name}</strong> `;
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'ghost branch-restore-button';
      button.textContent = 'Restore';
      button.addEventListener('click', async () => {
        const response = await fetch(`/api/projects/${projectId}/branches/${branch.id}/restore`, { method: 'POST' });
        const file = await response.json();
        if (activeFile?.id === file.id) {
          editor.value = file.content;
          renderHighlight(file.content);
        }
      });
      li.appendChild(button);
      branchList.appendChild(li);
    });
  };

  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const user = `browser-${Math.random().toString(16).slice(2, 8)}`;
  const socket = new WebSocket(`${scheme}://${window.location.host}/ws/projects/${projectId}?user=${user}`);
  socket.addEventListener('message', (event) => {
    const payload = JSON.parse(event.data);
    if (payload.type === 'presence') presenceStatus.textContent = `${payload.user} ${payload.status}`;
    if (payload.type === 'edit' && payload.path === activeFile?.path) {
      editor.value = payload.content;
      renderHighlight(payload.content);
      presenceStatus.textContent = `${payload.user} updated ${payload.path}`;
    }
    if (payload.type === 'cursor') presenceStatus.textContent = `${payload.user} is at line ${payload.line}`;
    if (payload.type === 'sync') presenceStatus.textContent = `Connected with ${payload.users.length} participant(s)`;
  });

  editor?.addEventListener('input', () => {
    renderHighlight(editor.value);
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      socket.send(JSON.stringify({ type: 'edit', path: activeFile.path, content: editor.value }));
    }, 200);
  });

  editor?.addEventListener('keyup', () => {
    const line = editor.value.slice(0, editor.selectionStart).split('\n').length;
    socket.send(JSON.stringify({ type: 'cursor', path: activeFile.path, line, column: 1 }));
  });

  compileButton?.addEventListener('click', async () => {
    const response = await fetch(`/api/projects/${projectId}/compile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine: engineSelect.value, entrypoint: activeFile?.path || 'main.tex', trigger: 'manual' }),
    });
    const job = await response.json();
    compileLog.textContent = job.log;
    pdfFrame.src = job.pdf_url;
  });

  snapshotButton?.addEventListener('click', async () => {
    if (!activeFile?.id) return;
    const response = await fetch(`/api/projects/${projectId}/snapshots`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: activeFile.id, name: `Snapshot ${new Date().toLocaleTimeString()}` }),
    });
    const snap = await response.json();
    addSnapshotOption(snap);
  });

  commentForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const formData = Object.fromEntries(new FormData(commentForm).entries());
    const response = await fetch(`/api/projects/${projectId}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...formData, file_id: activeFile.id, line_from: 1, line_to: 1 }),
    });
    const comment = await response.json();
    await refreshComments();
    commentForm.reset();
  });

  fileForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(fileForm).entries());
    const response = await fetch(`/api/projects/${projectId}/files`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const file = await response.json();
    const li = document.createElement('li');
    li.className = 'file-item';
    li.dataset.fileId = file.id;
    li.dataset.filePath = file.path;
    li.dataset.fileContent = file.content;
    li.textContent = file.path;
    attachFileItem(li);
    fileList.appendChild(li);
    fileItems = [...document.querySelectorAll('.file-item')];
    selectFile(li);
    fileForm.reset();
  });

  renameFileButton?.addEventListener('click', async () => {
    if (!activeFile?.id) return;
    const nextPath = window.prompt('New path for this file', activeFile.path);
    if (!nextPath || nextPath === activeFile.path) return;
    const response = await fetch(`/api/files/${activeFile.id}/move`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: nextPath }),
    });
    const file = await response.json();
    const activeNode = document.querySelector(`.file-item[data-file-id="${file.id}"]`);
    if (activeNode) {
      activeNode.dataset.filePath = file.path;
      activeNode.textContent = file.path;
      selectFile(activeNode);
    }
  });

  deleteFileButton?.addEventListener('click', async () => {
    if (!activeFile?.id) return;
    if (!window.confirm(`Delete ${activeFile.path}?`)) return;
    const response = await fetch(`/api/files/${activeFile.id}`, { method: 'DELETE' });
    if (!response.ok) return;
    const activeNode = document.querySelector(`.file-item[data-file-id="${activeFile.id}"]`);
    activeNode?.remove();
    fileItems = [...document.querySelectorAll('.file-item')];
    if (fileItems.length) {
      selectFile(fileItems[0]);
    } else {
      activeFile = null;
      editor.value = '';
    }
  });

  aiForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(aiForm).entries());
    const response = await fetch(`/api/projects/${projectId}/ai/assist`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    aiOutput.textContent = `${data.summary}\n\n${data.suggestion}`;
  });

  shareForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(shareForm).entries());
    const response = await fetch(`/api/projects/${projectId}/share-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, expires_in_days: 14 }),
    });
    if (!response.ok) {
      shareStatus.textContent = 'Share link creation requires owner access.';
      return;
    }
    const data = await response.json();
    shareStatus.textContent = `Created ${data.role} link: ${data.url}`;
  });

  referenceForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(referenceForm).entries());
    const response = await fetch(`/api/projects/${projectId}/references/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    const li = document.createElement('li');
    li.innerHTML = `<strong>${data.citation_key}</strong> — ${data.title}${data.duplicate ? ' (duplicate)' : ''}`;
    referenceList.prepend(li);
    referenceForm.reset();
  });

  suggestionForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(suggestionForm).entries());
    const createResponse = await fetch(`/api/projects/${projectId}/suggestions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, file_id: activeFile.id }),
    });
    const suggestion = await createResponse.json();
    const acceptResponse = await fetch(`/api/projects/${projectId}/suggestions/${suggestion.id}/accept`, { method: 'POST' });
    const accepted = await acceptResponse.json();
    editor.value = accepted.file.content;
    renderHighlight(accepted.file.content);
    suggestionStatus.textContent = `Accepted suggestion from ${suggestion.author}.\n\n${accepted.file.content}`;
  });

  branchForm?.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = Object.fromEntries(new FormData(branchForm).entries());
    const response = await fetch(`/api/projects/${projectId}/branches`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) return;
    branchForm.reset();
    refreshBranches();
  });

  refreshComments();
  refreshBranches();
}
