(function () {
  'use strict';

  var API = '/api/v1';
  var NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
  var MAX_BYTES = 65536;

  var els = {
    list: document.getElementById('file-list'),
    empty: document.getElementById('empty-note'),
    newBtn: document.getElementById('new-file'),
    fixturesBtn: document.getElementById('load-fixtures'),
    name: document.getElementById('file-name'),
    text: document.getElementById('file-text'),
    save: document.getElementById('save'),
    meta: document.getElementById('file-meta'),
    dirty: document.getElementById('dirty-flag'),
    status: document.getElementById('status'),
    conflict: document.getElementById('conflict'),
    loadLatest: document.getElementById('load-latest'),
    keepMine: document.getElementById('keep-mine')
  };

  var encoder = new TextEncoder();

  // mode: 'none' | 'new' | 'existing'
  var state = {
    mode: 'none',
    name: '',
    baseText: '',
    revision: 0,
    size: 0,
    files: [],
    busy: false,
    latest: null
  };

  function byteLength(s) {
    return encoder.encode(s).length;
  }

  function setStatus(message, isError) {
    els.status.textContent = message;
    els.status.classList.toggle('error', Boolean(isError));
  }

  function isDirty() {
    if (state.mode === 'new') {
      return els.name.value !== '' || els.text.value !== '';
    }
    if (state.mode === 'existing') {
      return els.text.value !== state.baseText;
    }
    return false;
  }

  function updateChrome() {
    els.dirty.textContent = isDirty() ? 'Unsaved changes' : '';
    els.save.disabled = state.busy || state.mode === 'none';
    els.fixturesBtn.disabled = state.busy;
    if (state.mode === 'existing') {
      els.meta.textContent = 'Size: ' + byteLength(els.text.value) + ' bytes. Revision: ' + state.revision + '.';
    } else if (state.mode === 'new') {
      els.meta.textContent = 'Size: ' + byteLength(els.text.value) + ' bytes. Not saved yet.';
    } else {
      els.meta.textContent = 'No file open.';
    }
  }

  function hideConflict() {
    state.latest = null;
    els.conflict.hidden = true;
  }

  function showConflict(current) {
    state.latest = current;
    els.conflict.hidden = false;
  }

  function renderList() {
    var refocus = null;
    if (els.list.contains(document.activeElement)) {
      refocus = document.activeElement.textContent;
    }
    els.list.textContent = '';
    state.files.forEach(function (f) {
      var li = document.createElement('li');
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = f.name;
      if (state.mode === 'existing' && f.name === state.name) {
        b.setAttribute('aria-current', 'true');
      }
      li.appendChild(b);
      els.list.appendChild(li);
      if (refocus !== null && f.name === refocus) {
        b.focus();
      }
    });
    els.empty.hidden = state.files.length !== 0;
  }

  function showFile(file) {
    state.mode = 'existing';
    state.name = file.name;
    state.baseText = file.text;
    state.revision = file.revision;
    state.size = file.size;
    els.name.value = file.name;
    els.name.readOnly = true;
    els.text.disabled = false;
    els.text.value = file.text;
    hideConflict();
    renderList();
    updateChrome();
  }

  function request(method, path, body) {
    var opts = { method: method, cache: 'no-store', headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(path, opts).then(function (resp) {
      return resp.text().then(function (raw) {
        var data = null;
        try { data = JSON.parse(raw); } catch (e) { data = null; }
        return { network: false, ok: resp.ok, status: resp.status, data: data };
      });
    }, function () {
      return { network: true, ok: false, status: 0, data: null };
    });
  }

  function errorMessage(res) {
    if (res.network) {
      return 'Could not reach the server. Your text is kept. Try Save again.';
    }
    if (res.data && res.data.error && typeof res.data.error.message === 'string') {
      return res.data.error.message + ' Your text is kept.';
    }
    return 'The server sent an unexpected reply (status ' + res.status + '). Your text is kept.';
  }

  function refreshList() {
    return request('GET', API + '/files').then(function (res) {
      if (res.ok && res.data && Array.isArray(res.data.files)) {
        state.files = res.data.files;
        renderList();
      } else {
        setStatus(res.network ? 'Could not reach the server. Try again shortly.' : 'Could not load the file list.', true);
      }
      return res;
    });
  }

  var openTicket = 0;

  function confirmDiscard() {
    if (!isDirty()) { return true; }
    return window.confirm('You have unsaved changes. Discard them?');
  }

  function openFile(name) {
    if (state.busy) { setStatus('Wait for the save to finish.'); return; }
    if (state.mode === 'existing' && name === state.name && !isDirty()) { return; }
    if (!confirmDiscard()) { return; }
    setStatus('Opening ' + name + '...');
    var ticket = ++openTicket;
    request('GET', API + '/files/' + encodeURIComponent(name)).then(function (res) {
      if (ticket !== openTicket || state.busy) { return; }
      if (res.ok && res.data && typeof res.data.text === 'string') {
        showFile(res.data);
        setStatus('Opened ' + res.data.name + ' (revision ' + res.data.revision + ')');
      } else {
        setStatus(errorMessage(res).replace(' Your text is kept.', ''), true);
      }
    });
  }

  function startNew() {
    if (state.busy) { setStatus('Wait for the save to finish.'); return; }
    if (!confirmDiscard()) { return; }
    openTicket++;
    state.mode = 'new';
    state.name = '';
    state.baseText = '';
    state.revision = 0;
    hideConflict();
    els.name.readOnly = false;
    els.name.value = '';
    els.text.disabled = false;
    els.text.value = '';
    renderList();
    updateChrome();
    els.name.focus();
    setStatus('New file. Enter a name and text, then Save.');
  }

  function finishSave(res, sentText, verb) {
    state.busy = false;
    if (res.ok && res.data && typeof res.data.revision === 'number') {
      var d = res.data;
      state.mode = 'existing';
      state.name = d.name;
      state.baseText = sentText;
      state.revision = d.revision;
      state.size = d.size;
      els.name.value = d.name;
      els.name.readOnly = true;
      hideConflict();
      updateChrome();
      setStatus('Saved ' + d.name + ' (revision ' + d.revision + ')');
      refreshList();
      return;
    }
    if (res.status === 409 && res.data && res.data.error && res.data.error.code === 'conflict' && res.data.current) {
      showConflict(res.data.current);
      setStatus('Conflict: the server has revision ' + res.data.current.revision + '. Your text is kept. Choose Load latest or Keep mine and save.', true);
      els.loadLatest.focus();
    } else {
      setStatus(errorMessage(res), true);
    }
    updateChrome();
  }

  function save(forceRevision) {
    if (state.busy || state.mode === 'none') { return; }
    var text = els.text.value;
    if (byteLength(text) > MAX_BYTES) {
      setStatus('Text is larger than 65536 bytes. Shorten it, then Save.', true);
      return;
    }
    if (text.indexOf('\u0000') !== -1) {
      setStatus('Text cannot contain NUL characters.', true);
      return;
    }
    var req;
    if (state.mode === 'new') {
      var name = els.name.value;
      if (!NAME_RE.test(name) || name.indexOf('..') !== -1) {
        setStatus('File name must be 1 to 64 letters, digits, dot, dash or underscore, start with a letter or digit, and not contain "..".', true);
        els.name.focus();
        return;
      }
      state.busy = true;
      updateChrome();
      setStatus('Saving...');
      req = request('POST', API + '/files', { name: name, text: text });
    } else {
      var base = typeof forceRevision === 'number' ? forceRevision : state.revision;
      state.busy = true;
      updateChrome();
      setStatus('Saving...');
      req = request('PUT', API + '/files/' + encodeURIComponent(state.name), { text: text, base_revision: base });
    }
    req.then(function (res) { finishSave(res, text); });
  }

  function loadFixtures() {
    state.busy = true;
    updateChrome();
    setStatus('Loading example files...');
    request('POST', API + '/fixtures', {}).then(function (res) {
      state.busy = false;
      if (res.ok && res.data && Array.isArray(res.data.files)) {
        state.files = res.data.files;
        renderList();
        var n = Array.isArray(res.data.created) ? res.data.created.length : 0;
        setStatus(n > 0 ? 'Loaded example files: ' + res.data.created.join(', ') : 'Example files are already present.');
      } else {
        setStatus(errorMessage(res).replace(' Your text is kept.', ''), true);
      }
      updateChrome();
    });
  }

  function focusList() {
    var current = els.list.querySelector('button[aria-current="true"]') || els.list.querySelector('button');
    (current || els.newBtn).focus();
  }

  // Events
  els.list.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button') : null;
    if (b && els.list.contains(b)) { openFile(b.textContent); }
  });

  els.list.addEventListener('keydown', function (e) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') { return; }
    var buttons = Array.prototype.slice.call(els.list.querySelectorAll('button'));
    var i = buttons.indexOf(document.activeElement);
    if (i === -1 || buttons.length === 0) { return; }
    e.preventDefault();
    var next = e.key === 'ArrowDown' ? Math.min(i + 1, buttons.length - 1) : Math.max(i - 1, 0);
    buttons[next].focus();
  });

  els.newBtn.addEventListener('click', startNew);
  els.fixturesBtn.addEventListener('click', loadFixtures);
  els.save.addEventListener('click', function () { save(); });
  els.loadLatest.addEventListener('click', function () {
    if (state.latest) {
      var cur = state.latest;
      showFile(cur);
      setStatus('Loaded latest ' + cur.name + ' (revision ' + cur.revision + ')');
      els.text.focus();
    }
  });
  els.keepMine.addEventListener('click', function () {
    if (state.latest) { save(state.latest.revision); }
  });

  function onInput() { updateChrome(); }
  els.text.addEventListener('input', onInput);
  els.name.addEventListener('input', onInput);

  function onEscape(e) {
    if (e.key === 'Escape') {
      e.preventDefault();
      focusList();
    }
  }
  els.text.addEventListener('keydown', onEscape);
  els.name.addEventListener('keydown', onEscape);

  document.addEventListener('keydown', function (e) {
    var key = (e.key || '').toLowerCase();
    if ((e.ctrlKey || e.metaKey) && !e.altKey && key === 's') {
      e.preventDefault();
      save();
    } else if (e.altKey && !e.ctrlKey && !e.metaKey && (key === 'n' || e.code === 'KeyN')) {
      e.preventDefault();
      startNew();
    }
  });

  window.addEventListener('beforeunload', function (e) {
    if (isDirty()) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  // Initial state
  els.text.disabled = true;
  updateChrome();
  refreshList().then(function (res) {
    if (res.ok && state.files.length === 0) {
      setStatus('No files yet. Choose New file or Load example files.');
    }
  });
})();
