/* =============================================================
   Conduit — app.js
   ============================================================= */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
  folders: [],
  files: [],
  totalFiles: 0,
  selectedIds: new Set(),
  filters: {
    folder_id: '',
    resolution: '',
    codec: '',
    hdr: '',
    audio_lang: '',
    audio_codec: '',
    needs_optimize: '',
  },
  search: '',
  sort: { col: 'filename', dir: 'asc' },
  pagination: { offset: 0, limit: 100 },
  scanStatus: { scanning: false },
  jobs: [],
  currentProgress: null,
  activeQueueTab: 'queue',
  logLines: [],
  _logPollTimer: null,
  _pendingHdrFileIds: [],
  _pendingNonHdrFileIds: [],
  _pendingKeepOriginal: false,
  _pendingEncodeOverrides: null,
  _ceKeepOriginal: false,
  _ceHdrAction: 'remux',
  _ceOutputDir: null,
  _loadedNetworkSettings: null,
  flaggedFiles: [],
  openFileId: null,
  bitrateThreshold: 25000,
};

// ---------------------------------------------------------------------------
// DOM references (lazily populated after DOMContentLoaded)
// ---------------------------------------------------------------------------

const $ = id => document.getElementById(id);
const DOM = {};

function initDOM() {
  DOM.scanIndicator  = $('scan-indicator');
  DOM.scanLabel      = $('scan-label');
  DOM.scanIdle       = $('scan-idle');
  DOM.folderList     = $('folder-list');
  DOM.addFolderBtn   = $('add-folder-btn');

  DOM.filterFolder   = $('filter-folder');
  DOM.filterRes      = $('filter-resolution');
  DOM.filterCodec    = $('filter-codec');
  DOM.filterHdr      = $('filter-hdr');
  DOM.filterLang      = $('filter-audio-lang');
  DOM.filterAudioCodec = $('filter-audio-codec');
  DOM.filterOpt       = $('filter-optimize');
  DOM.searchInput    = $('search-input');

  DOM.fileCountLabel = $('file-count-label');
  DOM.prevPageBtn    = $('prev-page-btn');
  DOM.nextPageBtn    = $('next-page-btn');
  DOM.pageLabel      = $('page-label');
  DOM.optimizeBtn    = $('optimize-btn');

  DOM.fileTbody      = $('file-tbody');
  DOM.selectAllCb    = $('select-all-cb');

  DOM.queuePanel     = $('queue-panel');
  DOM.queueToggle    = $('queue-toggle');
  DOM.queueCountBadge = $('queue-count-badge');
  DOM.progressSection = $('progress-section');
  DOM.progressFilename = $('progress-filename');
  DOM.progressBadge   = $('progress-badge');
  DOM.progressFill    = $('progress-fill');
  DOM.progressPercent = $('progress-percent');
  DOM.progressFps     = $('progress-fps');
  DOM.progressSpeed   = $('progress-speed');
  DOM.progressEta     = $('progress-eta');
  DOM.queueList       = $('queue-list');

  DOM.addFolderModal  = $('add-folder-modal');
  DOM.folderPathInput = $('folder-path-input');
  DOM.addFolderError  = $('add-folder-error');
  DOM.confirmAddFolderBtn = $('confirm-add-folder-btn');

  DOM.hdrModal        = $('hdr-modal');
  DOM.hdrFilesList    = $('hdr-modal-files-list');
  DOM.hdrRemuxBtn     = $('hdr-remux-btn');
  DOM.hdrReencodeBtn  = $('hdr-reencode-btn');

  DOM.flaggedPanel      = $('flagged-panel');
  DOM.flaggedToggle     = $('flagged-toggle');
  DOM.flaggedCountBadge = $('flagged-count-badge');
  DOM.flaggedBreakdown  = $('flagged-breakdown');
  DOM.flaggedList       = $('flagged-list');

  DOM.fileDetailDrawer    = $('file-detail-drawer');
  DOM.drawerFilename      = $('drawer-filename');
  DOM.drawerBody          = $('drawer-body');
  DOM.drawerClose         = $('drawer-close');
  DOM.drawerOptimizeBtn   = $('drawer-optimize-btn');

  DOM.encodeLog   = $('encode-log');
  DOM.historyList = $('history-list');

  DOM.optimizeConfirmModal  = $('optimize-confirm-modal');
  DOM.optimizeConfirmCount  = $('optimize-confirm-count');
  DOM.optimizeReplaceBtn    = $('optimize-replace-btn');
  DOM.optimizeKeepBtn       = $('optimize-keep-btn');

  DOM.encodeBtn             = $('encode-btn');
  DOM.customEncodeModal     = $('custom-encode-modal');
  DOM.customEncodeCount     = $('custom-encode-count');
  DOM.cePreset              = $('ce-preset');
  DOM.ceHwEncoder           = $('ce-hw-encoder');
  DOM.ceOutputCodec         = $('ce-output-codec');
  DOM.ceCq                  = $('ce-cq');
  DOM.ceCqDisplay           = $('ce-cq-display');
  DOM.ceAudioAction         = $('ce-audio-action');
  DOM.ceContainer           = $('ce-container');
  DOM.ceScaleHeight         = $('ce-scale-height');
  DOM.cePixFmt              = $('ce-pix-fmt');
  DOM.ceEncoderSpeed        = $('ce-encoder-speed');
  DOM.ceSubtitleMode        = $('ce-subtitle-mode');
  DOM.ceForceStereo         = $('ce-force-stereo');
  DOM.ceAudioNormalize      = $('ce-audio-normalize');
  DOM.ceOutputDir           = $('ce-output-dir');
  DOM.ceBrowseBtn           = $('ce-browse-btn');
  DOM.ceClearDirBtn         = $('ce-clear-dir-btn');
  DOM.ceAfterSection        = $('ce-after-section');
  DOM.collisionModal        = $('collision-modal');
  DOM.collisionDirLabel     = $('collision-dir-label');
  DOM.collisionList         = $('collision-list');
  DOM.collisionCancelBtn    = $('collision-cancel-btn');
  DOM.collisionConfirmBtn   = $('collision-confirm-btn');
  // CE HDR handling
  DOM.ceHdrSection          = $('ce-hdr-section');
  DOM.ceHdrCount            = $('ce-hdr-count');
  DOM.ceHdrFiles            = $('ce-hdr-files');
  DOM.ceHdrRemuxBtn         = $('ce-hdr-remux-btn');
  DOM.ceHdrReencodeBtn      = $('ce-hdr-reencode-btn');
  DOM.ceReplaceBtn          = $('ce-replace-btn');
  DOM.ceKeepBtn             = $('ce-keep-btn');
  DOM.ceSubmitBtn           = $('ce-submit-btn');
  DOM.ceError               = $('ce-error');

  DOM.settingsBtn           = $('settings-btn');
  DOM.settingsModal         = $('settings-modal');
  DOM.settingsHwEncoder      = $('settings-hw-encoder');
  DOM.settingsVaapiDevice    = $('settings-vaapi-device');
  DOM.settingsFfmpeg         = $('settings-ffmpeg');
  DOM.settingsFfprobe        = $('settings-ffprobe');
  DOM.settingsOutputCodec    = $('settings-output-codec');
  DOM.settingsCq             = $('settings-cq');
  DOM.settingsCqDisplay      = $('settings-cq-display');
  DOM.settingsOutputContainer = $('settings-output-container');
  DOM.settingsScaleHeight    = $('settings-scale-height');
  DOM.settingsPixFmt         = $('settings-pix-fmt');
  DOM.settingsEncoderSpeed   = $('settings-encoder-speed');
  DOM.settingsSubtitleMode   = $('settings-subtitle-mode');
  DOM.settingsAudioAction    = $('settings-audio-action');
  DOM.settingsLangAll        = $('settings-lang-all');
  DOM.settingsLangChips      = $('settings-lang-chips');
  DOM.settingsForceStereo    = $('settings-force-stereo');
  DOM.settingsAudioNormalize = $('settings-audio-normalize');
  DOM.settingsThreshold      = $('settings-threshold');
  DOM.settingsFlagAv1        = $('settings-flag-av1');
  DOM.settingsSaveBtn        = $('settings-save-btn');
  DOM.settingsError          = $('settings-error');
  DOM.settingsSuccess        = $('settings-success');
  DOM.settingsRestartNote    = $('settings-restart-note');
  DOM.settingsWebUiEnabled   = $('settings-web-ui-enabled');
  DOM.settingsWebUiHost      = $('settings-web-ui-host');
  DOM.settingsWebUiPort      = $('settings-web-ui-port');
  DOM.settingsWebUiUsername  = $('settings-web-ui-username');
  DOM.settingsWebUiPassword  = $('settings-web-ui-password');
  DOM.settingsNetworkFields  = $('settings-network-fields');

  DOM.aboutBtn   = $('about-btn');
  DOM.aboutModal = $('about-modal');

  DOM.flagPopover        = $('flag-popover');
  DOM.flagPopoverContent = $('flag-popover-content');
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

function getAuthHeader() {
  const user = localStorage.getItem('settings-web-ui-username');
  const pass = localStorage.getItem('settings-web-ui-password');
  if (user && pass) {
    return { 'Authorization': 'Basic ' + btoa(user + ':' + pass) };
  }
  return {};
}

async function api(method, path, body) {
  const opts = {
    method,
    headers: { ...getAuthHeader() },
  };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    const user = prompt('Enter Web UI Username:');
    const pass = prompt('Enter Web UI Password:');
    if (user && pass) {
      localStorage.setItem('settings-web-ui-username', user);
      localStorage.setItem('settings-web-ui-password', pass);
      return api(method, path, body); // retry
    }
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

const GET    = path       => api('GET',    path);
const POST   = (path, b)  => api('POST',   path, b);
const PUT    = (path, b)  => api('PUT',    path, b);
const DELETE = path       => api('DELETE', path);

const escHtml = s => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

// ---------------------------------------------------------------------------
// Formatters
// ---------------------------------------------------------------------------

function fmtSize(bytes) {
  if (!bytes) return '—';
  const gb = bytes / 1e9;
  if (gb >= 1) return gb.toFixed(2) + ' GB';
  return (bytes / 1e6).toFixed(0) + ' MB';
}

function fmtBitrate(kbps) {
  if (!kbps) return '—';
  if (kbps >= 1000) return (kbps / 1000).toFixed(1) + ' Mbps';
  return kbps + ' kbps';
}

function fmtResolution(w, h) {
  if (!w || !h) return '—';
  if (w >= 3840) return `4K (${w}×${h})`;
  if (w >= 1920) return `1080p`;
  if (w >= 1280) return `720p`;
  if (w >= 720)  return `480p`;
  return `${w}×${h}`;
}

function fmtDuration(s) {
  if (!s) return '—';
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
  return `${m}:${String(sec).padStart(2,'0')}`;
}

function fmtEta(sec) {
  if (sec == null) return '—';
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  if (m < 60) return `${m}m ${s}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

function codecLabel(codec) {
  if (!codec) return '—';
  const map = {
    hevc: 'HEVC',
    h264: 'H.264',
    av1:  'AV1',
    vp9:  'VP9',
    mpeg2video: 'MPEG-2',
    mpeg4: 'MPEG-4',
    vp8: 'VP8',
    wmv3: 'WMV',
    theora: 'Theora',
  };
  return map[codec] || codec.toUpperCase();
}

function codecBadgeClass(codec) {
  if (!codec) return 'badge-codec';
  if (codec === 'hevc') return 'badge badge-hevc';
  if (codec === 'h264') return 'badge badge-h264';
  if (codec === 'av1')  return 'badge badge-av1';
  return 'badge badge-codec';
}

function hdrBadgeHtml(hdrType) {
  if (!hdrType) return '<span class="badge badge-sdr">SDR</span>';
  const labels = {
    hdr10: 'HDR10',
    hdr10plus: 'HDR10+',
    dolby_vision: 'Dolby Vision',
    hlg: 'HLG',
  };
  const label = labels[hdrType] || hdrType.toUpperCase();
  return `<span class="badge badge-${hdrType}">${label}</span>`;
}

function langLabel(lang) {
  const map = { eng: 'EN', jpn: 'JA', fre: 'FR', ger: 'DE', spa: 'ES', chi: 'ZH',
                ita: 'IT', por: 'PT', rus: 'RU', kor: 'KO', ara: 'AR', hin: 'HI' };
  return map[lang] || (lang || '??').toUpperCase().slice(0, 3);
}

function langBadgeClass(lang) {
  if (lang === 'eng') return 'badge badge-lang badge-lang-eng';
  if (lang === 'jpn') return 'badge badge-lang badge-lang-jpn';
  return 'badge badge-lang';
}

function fmtChannels(ch) {
  if (!ch) return '';
  if (ch === 1) return 'Mono';
  if (ch === 2) return '2.0';
  if (ch === 6) return '5.1';
  if (ch === 8) return '7.1';
  return `${ch}ch`;
}

function audioTrackLabel(t) {
  const codec = (t.codec_name || '').toLowerCase();
  const profile = (t.profile || '').toLowerCase();
  if (codec === 'dts') {
    if (profile.includes('ma'))  return 'DTS-HD MA';
    if (profile.includes('hra')) return 'DTS-HD HRA';
    if (profile.includes('es'))  return 'DTS-ES';
    return 'DTS';
  }
  const map = {
    eac3: 'EAC3', ac3: 'AC3', aac: 'AAC', opus: 'Opus',
    flac: 'FLAC', mp3: 'MP3', truehd: 'TrueHD', pcm_s16le: 'PCM',
    pcm_s24le: 'PCM', vorbis: 'Vorbis',
  };
  return map[codec] || (t.codec_name || '').toUpperCase();
}

function getFlagReasons(file) {
  const reasons = [];
  if (file.video_codec === 'h264' && file.pix_fmt && file.pix_fmt.includes('10')) reasons.push('hi10p');
  if (file.video_codec === 'av1') reasons.push('av1');
  if (file.bitrate_kbps > state.bitrateThreshold) reasons.push('bitrate');
  return reasons;
}

// ---------------------------------------------------------------------------
// Flag reason popover
// ---------------------------------------------------------------------------

let _flagPopoverAnchor = null;

function flagReasonDetail(reason, file) {
  if (reason === 'hi10p') return {
    badgeCls: 'flag-reason-hi10p', badgeText: 'Hi10P',
    desc: 'H.264 with 10-bit color (Hi10P) — 10-bit H.264 has poor hardware decode support. Re-encoding to HEVC preserves quality with broader compatibility.',
  };
  if (reason === 'av1') return {
    badgeCls: 'flag-reason-av1', badgeText: 'AV1',
    desc: 'AV1 codec — flagged for re-encoding to a hardware-accelerated codec. You can disable AV1 flagging in Settings → Flagging.',
  };
  if (reason === 'bitrate') {
    const mbps = file.bitrate_kbps ? (file.bitrate_kbps / 1000).toFixed(1) : '?';
    return {
      badgeCls: 'flag-reason-bitrate', badgeText: 'High Bitrate',
      desc: `Bitrate is ${mbps} Mbps, which exceeds the configured threshold. Re-encoding will significantly reduce file size.`,
    };
  }
  return { badgeCls: '', badgeText: reason, desc: '' };
}

function showFlagPopover(anchorEl, file) {
  const reasons = getFlagReasons(file);
  if (!reasons.length) return;

  DOM.flagPopoverContent.innerHTML = reasons.map(r => {
    const d = flagReasonDetail(r, file);
    return `<div class="flag-popover-row">
      <span class="flag-reason-badge ${d.badgeCls}">${d.badgeText}</span>
      <span class="flag-popover-desc">${d.desc}</span>
    </div>`;
  }).join('');

  const pop = DOM.flagPopover;
  pop.classList.remove('hidden');

  const rect = anchorEl.getBoundingClientRect();
  const popW = 300;
  let left = rect.left + rect.width / 2 - popW / 2;
  left = Math.max(8, Math.min(left, window.innerWidth - popW - 8));
  pop.style.width = `${popW}px`;
  pop.style.left = `${left}px`;

  // Position above the anchor if there's room, otherwise below
  const popH = pop.offsetHeight;
  if (rect.top - popH - 8 > 0) {
    pop.style.top = `${rect.top + window.scrollY - popH - 8}px`;
  } else {
    pop.style.top = `${rect.bottom + window.scrollY + 8}px`;
  }

  _flagPopoverAnchor = anchorEl;
}

function hideFlagPopover() {
  DOM.flagPopover.classList.add('hidden');
  _flagPopoverAnchor = null;
}

function shortenPath(p, maxLen = 18) {
  if (!p) return '';
  const parts = p.split('/').filter(Boolean);
  const name = parts[parts.length - 1] || p;
  return name.length > maxLen ? '…' + name.slice(-maxLen) : name;
}

// ---------------------------------------------------------------------------
// Folders
// ---------------------------------------------------------------------------

async function fetchFolders() {
  try {
    state.folders = await GET('/api/folders');
    renderSidebar();
    syncFolderFilterDropdown();
  } catch (e) {
    console.error('fetchFolders:', e);
  }
}

function renderSidebar() {
  const list = DOM.folderList;
  list.innerHTML = '';

  if (state.folders.length === 0) {
    const li = document.createElement('li');
    li.className = 'folder-item';
    li.innerHTML = `<div class="folder-item-inner text-muted" style="font-size:12px;cursor:default;">No folders added</div>`;
    list.appendChild(li);
    return;
  }

  for (const folder of state.folders) {
    const li = document.createElement('li');
    li.className = 'folder-item';

    const isActive = String(state.filters.folder_id) === String(folder.id);
    const inner = document.createElement('div');
    inner.className = 'folder-item-inner' + (isActive ? ' active' : '');
    inner.dataset.folderId = folder.id;

    inner.innerHTML = `
      <svg class="folder-icon" viewBox="0 0 24 24" fill="none">
        <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"
              stroke="currentColor" stroke-width="1.4" fill="none"/>
      </svg>
      <div style="flex:1;min-width:0;">
        <div class="folder-name" title="${folder.path}">${shortenPath(folder.path)}</div>
        <div class="folder-meta"><span>${folder.file_count} files</span><span>${fmtSize(folder.total_size || 0)}</span></div>
      </div>
      <span class="folder-actions">
        <button class="folder-action-btn scan-btn" title="Scan folder" data-id="${folder.id}">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M4 4v5h5M20 20v-5h-5M4 9A9 9 0 0 1 20 9M20 15a9 9 0 0 1-16 0"
                  stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </button>
        <button class="folder-action-btn delete" title="Remove folder" data-id="${folder.id}">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
        </button>
      </span>
    `;

    inner.addEventListener('click', e => {
      if (e.target.closest('.folder-action-btn')) return;
      const newId = isActive ? '' : String(folder.id);
      state.filters.folder_id = newId;
      DOM.filterFolder.value = newId;
      applyFilters();
    });

    inner.querySelector('.scan-btn').addEventListener('click', e => {
      e.stopPropagation();
      triggerScan(folder.id);
    });

    inner.querySelector('.folder-action-btn.delete').addEventListener('click', e => {
      e.stopPropagation();
      deleteFolder(folder.id);
    });

    li.appendChild(inner);
    list.appendChild(li);
  }
}

function syncFolderFilterDropdown() {
  const sel = DOM.filterFolder;
  const current = sel.value;
  while (sel.options.length > 1) sel.remove(1);
  for (const f of state.folders) {
    const opt = document.createElement('option');
    opt.value = f.id;
    opt.textContent = shortenPath(f.path, 30);
    sel.appendChild(opt);
  }
  sel.value = current;
}

async function deleteFolder(id) {
  if (!confirm('Remove this folder from Conduit? Files on disk are NOT deleted.')) return;
  try {
    await DELETE(`/api/folders/${id}`);
    if (String(state.filters.folder_id) === String(id)) {
      state.filters.folder_id = '';
    }
    await fetchFolders();
    applyFilters();
  } catch (e) {
    alert('Error removing folder: ' + e.message);
  }
}

async function triggerScan(folderId) {
  try {
    await POST(`/api/folders/${folderId}/scan`);
  } catch (e) {
    alert('Error starting scan: ' + e.message);
  }
}

// ---------------------------------------------------------------------------
// Files
// ---------------------------------------------------------------------------

async function fetchFiles() {
  const params = new URLSearchParams();
  if (state.filters.folder_id)   params.set('folder_id',     state.filters.folder_id);
  if (state.filters.resolution)  params.set('resolution',    state.filters.resolution);
  if (state.filters.codec)       params.set('codec',         state.filters.codec);
  if (state.filters.hdr)         params.set('hdr',           state.filters.hdr);
  if (state.filters.audio_lang)  params.set('audio_lang',    state.filters.audio_lang);
  if (state.filters.audio_codec) params.set('audio_codec',   state.filters.audio_codec);
  if (state.filters.needs_optimize !== '')
                                  params.set('needs_optimize', state.filters.needs_optimize);
  if (state.search)              params.set('search',        state.search);
  params.set('sort',   state.sort.col);
  params.set('dir',    state.sort.dir);
  params.set('limit',  state.pagination.limit);
  params.set('offset', state.pagination.offset);

  try {
    const data = await GET('/api/files?' + params.toString());
    state.files     = data.files;
    state.totalFiles = data.total;
    renderTable();
    updatePagination();
  } catch (e) {
    console.error('fetchFiles:', e);
  }
}

function renderTable() {
  const tbody = DOM.fileTbody;
  tbody.innerHTML = '';

  const { offset, limit } = state.pagination;
  const from = state.totalFiles === 0 ? 0 : offset + 1;
  const to   = Math.min(offset + limit, state.totalFiles);
  DOM.fileCountLabel.textContent = `${state.totalFiles.toLocaleString()} file${state.totalFiles !== 1 ? 's' : ''}`;
  DOM.pageLabel.textContent = `${from} – ${to} of ${state.totalFiles.toLocaleString()}`;

  if (state.files.length === 0) {
    const tr = document.createElement('tr');
    tr.className = 'empty-row';
    tr.innerHTML = `<td colspan="12">No files match the current filters.</td>`;
    tbody.appendChild(tr);
    DOM.selectAllCb.checked = false;
    DOM.selectAllCb.indeterminate = false;
    updateOptimizeBtn();
    return;
  }

  for (const file of state.files) {
    const tr = buildFileRow(file);
    tbody.appendChild(tr);
  }

  syncSelectAllCheckbox();
  updateOptimizeBtn();
}

function buildFileRow(file) {
  const tr = document.createElement('tr');
  const isSelected = state.selectedIds.has(file.id);
  if (isSelected) tr.classList.add('selected');

  let audioHtml = '<div class="audio-cell">';
  try {
    const tracks = JSON.parse(file.audio_tracks || '[]');
    for (const t of tracks) {
      const lang = t.language || '';
      const langClass = langBadgeClass(lang);
      const langTxt = langLabel(lang);
      const codecLbl = audioTrackLabel(t);
      const chLbl = fmtChannels(t.channels);
      const title = `${lang} · ${codecLbl}${chLbl ? ' · ' + chLbl : ''}`;
      audioHtml += `<div class="audio-track" title="${title}">`;
      audioHtml += `<span class="${langClass}">${langTxt}</span>`;
      audioHtml += `<span class="audio-track-codec">${codecLbl}</span>`;
      if (chLbl) audioHtml += `<span class="audio-track-channels">${chLbl}</span>`;
      audioHtml += `</div>`;
    }
    if (tracks.length === 0) audioHtml += '<span style="font-size:11px;color:var(--text-muted)">—</span>';
  } catch {}
  audioHtml += '</div>';

  let subHtml = '<div class="sub-cell">';
  try {
    const subs = JSON.parse(file.subtitle_tracks || '[]');
    const uniq = {};
    for (const s of subs) {
      const lang = s.language || 'und';
      if (!uniq[lang]) {
        uniq[lang] = true;
        subHtml += `<span class="${langBadgeClass(lang)}">${langLabel(lang)}</span>`;
      }
    }
    if (Object.keys(uniq).length === 0) subHtml += '<span class="text-muted" style="font-size:11px">—</span>';
  } catch {}
  subHtml += '</div>';

  const optHtml = file.needs_optimize
    ? `<button class="opt-flag opt-flag-yes flag-popover-trigger" title="Click to see why flagged">
         <svg viewBox="0 0 24 24" fill="none"><path d="M13 10V3L4 14h7v7l9-11h-7z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
       </button>`
    : '';

  const bitrateClass = file.bitrate_kbps > state.bitrateThreshold ? 'cell-bitrate bitrate-high' : 'cell-bitrate';

  tr.innerHTML = `
    <td class="col-check"><input type="checkbox" data-id="${file.id}" ${isSelected ? 'checked' : ''} /></td>
    <td class="col-filename"><span class="cell-filename" title="${file.filename}">${file.filename}</span></td>
    <td class="col-folder"><span class="cell-folder" title="${file.folder_path || ''}">${shortenPath(file.folder_path || '')}</span></td>
    <td class="col-resolution"><span class="cell-resolution">${fmtResolution(file.width, file.height)}</span></td>
    <td class="col-hdr">${hdrBadgeHtml(file.hdr_type)}</td>
    <td class="col-codec"><span class="${codecBadgeClass(file.video_codec)}">${codecLabel(file.video_codec)}</span></td>
    <td class="col-audio">${audioHtml}</td>
    <td class="col-subs">${subHtml}</td>
    <td class="col-size"><span class="cell-size">${fmtSize(file.size_bytes)}</span></td>
    <td class="col-bitrate"><span class="${bitrateClass}">${fmtBitrate(file.bitrate_kbps)}</span></td>
    <td class="col-duration"><span class="cell-duration">${fmtDuration(file.duration_s)}</span></td>
    <td class="col-opt">${optHtml}</td>
  `;

  tr.addEventListener('click', e => {
    if (e.target.type === 'checkbox') return;
    const flagBtn = e.target.closest('.flag-popover-trigger');
    if (flagBtn) {
      e.stopPropagation();
      if (_flagPopoverAnchor === flagBtn) {
        hideFlagPopover();
      } else {
        showFlagPopover(flagBtn, file);
      }
      return;
    }
    openFileDetail(file);
  });

  const cb = tr.querySelector('input[type="checkbox"]');
  cb.addEventListener('change', () => {
    if (cb.checked) {
      state.selectedIds.add(file.id);
      tr.classList.add('selected');
    } else {
      state.selectedIds.delete(file.id);
      tr.classList.remove('selected');
    }
    syncSelectAllCheckbox();
    updateOptimizeBtn();
  });

  return tr;
}

function syncSelectAllCheckbox() {
  const visibleIds = state.files.map(f => f.id);
  const selectedVisible = visibleIds.filter(id => state.selectedIds.has(id));
  if (selectedVisible.length === 0) {
    DOM.selectAllCb.checked = false;
    DOM.selectAllCb.indeterminate = false;
  } else if (selectedVisible.length === visibleIds.length) {
    DOM.selectAllCb.checked = true;
    DOM.selectAllCb.indeterminate = false;
  } else {
    DOM.selectAllCb.checked = false;
    DOM.selectAllCb.indeterminate = true;
  }
}

function updateOptimizeBtn() {
  DOM.optimizeBtn.disabled = state.selectedIds.size === 0;
  DOM.encodeBtn.disabled   = state.selectedIds.size === 0;
}

// ---------------------------------------------------------------------------
// Filters, sorting, pagination
// ---------------------------------------------------------------------------

function applyFilters() {
  state.pagination.offset = 0;
  fetchFiles();
}

function updatePagination() {
  const { offset, limit } = state.pagination;
  DOM.prevPageBtn.disabled = offset === 0;
  DOM.nextPageBtn.disabled = offset + limit >= state.totalFiles;
}

function bindFilters() {
  DOM.filterFolder.addEventListener('change', () => {
    state.filters.folder_id = DOM.filterFolder.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterRes.addEventListener('change', () => {
    state.filters.resolution = DOM.filterRes.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterCodec.addEventListener('change', () => {
    state.filters.codec = DOM.filterCodec.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterHdr.addEventListener('change', () => {
    state.filters.hdr = DOM.filterHdr.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterLang.addEventListener('change', () => {
    state.filters.audio_lang = DOM.filterLang.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterAudioCodec.addEventListener('change', () => {
    state.filters.audio_codec = DOM.filterAudioCodec.value;
    saveFiltersToStorage(); applyFilters();
  });
  DOM.filterOpt.addEventListener('change', () => {
    state.filters.needs_optimize = DOM.filterOpt.value;
    saveFiltersToStorage(); applyFilters();
  });

  let searchTimer;
  DOM.searchInput.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = DOM.searchInput.value.trim();
      saveFiltersToStorage();
      applyFilters();
    }, 300);
  });

  DOM.prevPageBtn.addEventListener('click', () => {
    state.pagination.offset = Math.max(0, state.pagination.offset - state.pagination.limit);
    fetchFiles();
  });
  DOM.nextPageBtn.addEventListener('click', () => {
    state.pagination.offset += state.pagination.limit;
    fetchFiles();
  });
}

function bindSortHeaders() {
  document.querySelectorAll('#file-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      if (state.sort.col === col) {
        state.sort.dir = state.sort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.sort.col = col;
        state.sort.dir = 'asc';
      }
      updateSortArrows();
      saveFiltersToStorage();
      applyFilters();
    });
  });
}

function updateSortArrows() {
  document.querySelectorAll('#file-table th.sortable').forEach(th => {
    const arrow = th.querySelector('.sort-arrow');
    if (th.dataset.col === state.sort.col) {
      th.classList.add('sort-active');
      arrow.textContent = state.sort.dir === 'asc' ? ' ▲' : ' ▼';
    } else {
      th.classList.remove('sort-active');
      arrow.textContent = '';
    }
  });
}

// ---------------------------------------------------------------------------
// Select all
// ---------------------------------------------------------------------------

function bindSelectAll() {
  DOM.selectAllCb.addEventListener('change', () => {
    if (DOM.selectAllCb.checked) {
      state.files.forEach(f => state.selectedIds.add(f.id));
    } else {
      state.files.forEach(f => state.selectedIds.delete(f.id));
    }
    renderTable();
  });
}

// ---------------------------------------------------------------------------
// Optimize / HDR modal
// ---------------------------------------------------------------------------

function handleOptimize() {
  const selectedFiles = state.files.filter(f => state.selectedIds.has(f.id));
  if (selectedFiles.length === 0) return;

  const hdrFiles    = selectedFiles.filter(f => f.hdr_type === 'hdr10plus' || f.hdr_type === 'dolby_vision');
  const normalFiles = selectedFiles.filter(f => f.hdr_type !== 'hdr10plus' && f.hdr_type !== 'dolby_vision');

  state._pendingHdrFileIds    = hdrFiles.map(f => f.id);
  state._pendingNonHdrFileIds = normalFiles.map(f => f.id);

  const count = selectedFiles.length;
  DOM.optimizeConfirmCount.textContent = `${count} file${count !== 1 ? 's' : ''}`;
  openModal('optimize-confirm-modal');
}

// ---------------------------------------------------------------------------
// Presets
// ---------------------------------------------------------------------------

let _presetsCache = null;

async function _loadPresets(force = false) {
  if (_presetsCache && !force) return _presetsCache;
  const data = await GET('/api/presets');
  _presetsCache = [...data.builtin, ...data.user];
  return _presetsCache;
}

async function _populatePresetSelector() {
  const presets = await _loadPresets();
  const sel = DOM.cePreset;
  sel.innerHTML = '<option value="">— Custom —</option>';
  for (const p of presets) {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name + (p.builtin ? ' ★' : '');
    sel.appendChild(opt);
  }
}

async function loadPresetsTab() {
  _presetsCache = null;
  const presets = await _loadPresets();
  const list = $('presets-list');
  list.innerHTML = '';

  if (presets.length === 0) {
    list.innerHTML = '<div class="db-empty">No presets yet. Click "+ New Preset" to create one.</div>';
    return;
  }

  for (const p of presets) {
    const row = document.createElement('div');
    row.className = 'preset-row';
    const meta = [
      p.hw_encoder?.toUpperCase(),
      p.output_video_codec?.toUpperCase(),
      `CQ ${p.video_quality_cq}`,
      p.audio_lossy_action?.toUpperCase(),
      p.output_container?.toUpperCase(),
    ].filter(Boolean).join(' · ');

    row.innerHTML = `
      <div class="preset-row-info">
        <span class="preset-row-name">${escHtml(p.name)}${p.builtin ? ' <span class="preset-builtin-badge">built-in</span>' : ''}</span>
        <span class="preset-row-meta">${meta}</span>
        ${p.description ? `<span class="preset-row-desc">${escHtml(p.description)}</span>` : ''}
      </div>
      <div class="preset-row-actions">
        ${!p.builtin ? `<button class="btn-preset-edit" data-id="${p.id}">Edit</button><button class="btn-preset-delete" data-id="${p.id}">Delete</button>` : ''}
      </div>`;
    list.appendChild(row);
  }

  list.querySelectorAll('.btn-preset-edit').forEach(btn => {
    btn.addEventListener('click', () => _openPresetEditor(btn.dataset.id));
  });
  list.querySelectorAll('.btn-preset-delete').forEach(btn => {
    btn.addEventListener('click', () => _deletePreset(btn.dataset.id));
  });
}

function _openPresetEditor(presetId = null) {
  const editor = $('preset-editor');
  const title  = $('preset-editor-title');
  editor.dataset.editingId = presetId || '';

  if (presetId) {
    const p = _presetsCache?.find(x => x.id === presetId);
    if (!p) return;
    title.textContent = 'Edit Preset';
    $('pe-name').value        = p.name;
    $('pe-hw-encoder').value  = p.hw_encoder;
    $('pe-output-codec').value= p.output_video_codec;
    $('pe-container').value   = p.output_container;
    $('pe-cq').value          = p.video_quality_cq;
    $('pe-cq-display').textContent = p.video_quality_cq;
    $('pe-audio-action').value= p.audio_lossy_action;
  } else {
    title.textContent = 'New Preset';
    $('pe-name').value        = '';
    $('pe-hw-encoder').value  = 'nvenc';
    $('pe-output-codec').value= 'hevc';
    $('pe-container').value   = 'mkv';
    $('pe-cq').value          = 24;
    $('pe-cq-display').textContent = '24';
    $('pe-audio-action').value= 'opus';
  }

  editor.classList.remove('hidden');
  $('pe-name').focus();
}

async function _savePreset() {
  const editor = $('preset-editor');
  const editingId = editor.dataset.editingId;
  const name = $('pe-name').value.trim();
  if (!name) { $('pe-name').focus(); return; }

  const payload = {
    name,
    hw_encoder:         $('pe-hw-encoder').value,
    output_video_codec: $('pe-output-codec').value,
    video_quality_cq:   parseInt($('pe-cq').value, 10),
    audio_lossy_action: $('pe-audio-action').value,
    output_container:   $('pe-container').value,
  };

  try {
    if (editingId) {
      await PUT(`/api/presets/${editingId}`, payload);
    } else {
      await POST('/api/presets', payload);
    }
    editor.classList.add('hidden');
    loadPresetsTab();
  } catch (e) {
    alert('Failed to save preset.');
  }
}

async function _deletePreset(id) {
  if (!confirm('Delete this preset?')) return;
  try {
    await DELETE(`/api/presets/${id}`);
    loadPresetsTab();
  } catch (e) {
    alert('Failed to delete preset.');
  }
}

async function handleCustomEncode() {
  const selectedFiles = state.files.filter(f => state.selectedIds.has(f.id));
  if (selectedFiles.length === 0) return;

  const count = selectedFiles.length;
  DOM.customEncodeCount.textContent = `${count} file${count !== 1 ? 's' : ''}`;

  await _populatePresetSelector();

  try {
    const s = await GET('/api/settings');
    _ceApplySettings({
      hw_encoder:         s.hw_encoder         || 'nvenc',
      output_video_codec: s.output_video_codec  || 'hevc',
      video_quality_cq:   s.video_quality_cq    ?? 24,
      audio_lossy_action: s.audio_lossy_action  || 'opus',
      output_container:   s.output_container    || 'mkv',
      scale_height:       s.scale_height        ?? 0,
      pix_fmt:            s.pix_fmt             || 'auto',
      encoder_speed:      s.encoder_speed       || 'medium',
      subtitle_mode:      s.subtitle_mode       || 'copy',
      force_stereo:       s.force_stereo        || false,
      audio_normalize:    s.audio_normalize     || false,
    });
  } catch (_) {}

  DOM.cePreset.value = '';

  const hdrFiles = selectedFiles.filter(f => f.hdr_type === 'hdr10plus' || f.hdr_type === 'dolby_vision');
  if (hdrFiles.length > 0) {
    DOM.ceHdrSection.classList.remove('hidden');
    DOM.ceHdrCount.textContent = `(${hdrFiles.length})`;
    DOM.ceHdrFiles.innerHTML = hdrFiles.map(f =>
      `<div class="ce-hdr-file-item">${hdrBadgeHtml(f.hdr_type)}<span class="ce-hdr-file-name" title="${escHtml(f.path)}">${escHtml(f.filename)}</span></div>`
    ).join('');
    _ceSetHdrAction('remux');
  } else {
    DOM.ceHdrSection.classList.add('hidden');
  }

  _ceSetKeepOriginal(false);
  _ceSetOutputDir(null);
  openModal('custom-encode-modal');
}

function _ceApplySettings(p) {
  if (p.hw_encoder)         DOM.ceHwEncoder.value       = p.hw_encoder;
  if (p.output_video_codec) DOM.ceOutputCodec.value     = p.output_video_codec;
  if (p.video_quality_cq != null) {
    DOM.ceCq.value              = p.video_quality_cq;
    DOM.ceCqDisplay.textContent = p.video_quality_cq;
  }
  if (p.audio_lossy_action) DOM.ceAudioAction.value     = p.audio_lossy_action;
  if (p.output_container)   DOM.ceContainer.value       = p.output_container;
  if (p.scale_height != null) DOM.ceScaleHeight.value   = String(p.scale_height);
  if (p.pix_fmt)            DOM.cePixFmt.value          = p.pix_fmt;
  if (p.encoder_speed)      DOM.ceEncoderSpeed.value    = p.encoder_speed;
  if (p.subtitle_mode)      DOM.ceSubtitleMode.value    = p.subtitle_mode;
  if (p.force_stereo != null)    DOM.ceForceStereo.checked    = p.force_stereo;
  if (p.audio_normalize != null) DOM.ceAudioNormalize.checked = p.audio_normalize;
}

function _ceSetKeepOriginal(keep) {
  state._ceKeepOriginal = keep;
  DOM.ceReplaceBtn.classList.toggle('ce-choice-active', !keep);
  DOM.ceKeepBtn.classList.toggle('ce-choice-active', keep);
}

function _ceSetHdrAction(action) {
  state._ceHdrAction = action;
  DOM.ceHdrRemuxBtn.classList.toggle('ce-hdr-choice-active', action === 'remux');
  DOM.ceHdrReencodeBtn.classList.toggle('ce-hdr-choice-active', action === 'reencode');
}

function _ceSetOutputDir(dir) {
  state._ceOutputDir = dir || null;
  if (dir) {
    DOM.ceOutputDir.value = dir;
    DOM.ceClearDirBtn.classList.remove('hidden');
    DOM.ceAfterSection.style.display = 'none';
  } else {
    DOM.ceOutputDir.value = '';
    DOM.ceClearDirBtn.classList.add('hidden');
    DOM.ceAfterSection.style.display = '';
  }
}

function _detectOutputDirCollisions(files) {
  const stems = {};
  for (const f of files) {
    const stem = f.filename.replace(/\.[^/.]+$/, '');
    if (!stems[stem]) stems[stem] = [];
    stems[stem].push(f);
  }
  return Object.entries(stems).filter(([, group]) => group.length > 1);
}

function _showCollisionWarning(collisions, outputDir, onConfirm) {
  DOM.collisionDirLabel.textContent = outputDir;
  DOM.collisionList.innerHTML = collisions.map(([stem, files]) => `
    <div class="collision-group">
      <div class="collision-group-name">${escHtml(stem)}.*</div>
      <ul class="collision-group-files">
        ${files.map(f => `<li title="${escHtml(f.path)}">${escHtml(f.filename)}</li>`).join('')}
      </ul>
    </div>`).join('');

  const onConfirmClick = () => {
    DOM.collisionConfirmBtn.removeEventListener('click', onConfirmClick);
    closeModal('collision-modal');
    onConfirm();
  };
  DOM.collisionConfirmBtn.addEventListener('click', onConfirmClick);

  openModal('collision-modal');
}

async function _submitCustomEncode() {
  const selectedFiles = state.files.filter(f => state.selectedIds.has(f.id));
  if (selectedFiles.length === 0) return;

  DOM.ceError.classList.add('hidden');

  const ceCodec     = DOM.ceOutputCodec.value;
  const ceContainer = DOM.ceContainer.value;
  if (ceCodec === 'vp9' && ceContainer === 'mp4') {
    DOM.ceError.textContent = 'VP9 is not compatible with the MP4 container. Use MKV or WebM.';
    DOM.ceError.classList.remove('hidden');
    return;
  }
  if (ceContainer === 'webm' && !['vp9', 'av1'].includes(ceCodec)) {
    DOM.ceError.textContent = 'WebM only supports VP9 and AV1. Use MKV for H.264 or HEVC.';
    DOM.ceError.classList.remove('hidden');
    return;
  }

  if (state._ceOutputDir) {
    const collisions = _detectOutputDirCollisions(selectedFiles);
    if (collisions.length > 0) {
      _showCollisionWarning(collisions, state._ceOutputDir, () => {
        closeModal('custom-encode-modal');
        _doSubmitCustomEncode(selectedFiles);
      });
      return;
    }
  }

  closeModal('custom-encode-modal');
  _doSubmitCustomEncode(selectedFiles);
}

function _doSubmitCustomEncode(selectedFiles) {
  const ko = state._ceKeepOriginal;
  const overrides = {
    hw_encoder:         DOM.ceHwEncoder.value,
    output_video_codec: DOM.ceOutputCodec.value,
    video_quality_cq:   parseInt(DOM.ceCq.value, 10),
    audio_lossy_action: DOM.ceAudioAction.value,
    output_container:   DOM.ceContainer.value,
    scale_height:       parseInt(DOM.ceScaleHeight.value, 10) || null,
    pix_fmt:            DOM.cePixFmt.value,
    encoder_speed:      DOM.ceEncoderSpeed.value,
    subtitle_mode:      DOM.ceSubtitleMode.value,
    force_stereo:       DOM.ceForceStereo.checked,
    audio_normalize:    DOM.ceAudioNormalize.checked,
    output_dir:         state._ceOutputDir || null,
  };

  const hdrFiles    = selectedFiles.filter(f => f.hdr_type === 'hdr10plus' || f.hdr_type === 'dolby_vision');
  const normalFiles = selectedFiles.filter(f => f.hdr_type !== 'hdr10plus' && f.hdr_type !== 'dolby_vision');

  const jobs = [];
  if (normalFiles.length > 0) {
    jobs.push(submitJobs(normalFiles.map(f => f.id), 'encode', ko, overrides));
  }
  if (hdrFiles.length > 0) {
    if (state._ceHdrAction === 'remux') {
      jobs.push(submitJobs(hdrFiles.map(f => f.id), 'remux', ko, overrides));
    } else {
      jobs.push(submitJobs(hdrFiles.map(f => f.id), 'encode', ko, overrides));
    }
  }
  Promise.all(jobs);
}

function showHdrModal(hdrFiles) {
  const list = DOM.hdrFilesList;
  list.innerHTML = '';
  for (const f of hdrFiles) {
    const div = document.createElement('div');
    div.className = 'hdr-file-item';
    div.innerHTML = `${hdrBadgeHtml(f.hdr_type)}<span class="hdr-file-name" title="${f.filename}">${f.filename}</span>`;
    list.appendChild(div);
  }
  openModal('hdr-modal');
}

async function submitJobs(fileIds, jobType, keepOriginal = false, encodeOverrides = null) {
  if (!fileIds.length) return;
  try {
    const payload = { file_ids: fileIds, job_type: jobType, keep_original: keepOriginal };
    if (encodeOverrides) {
      payload.hw_encoder         = encodeOverrides.hw_encoder;
      payload.output_video_codec = encodeOverrides.output_video_codec;
      payload.video_quality_cq   = encodeOverrides.video_quality_cq;
      payload.audio_lossy_action = encodeOverrides.audio_lossy_action;
      payload.output_container   = encodeOverrides.output_container;
      if (encodeOverrides.scale_height != null)    payload.scale_height    = encodeOverrides.scale_height;
      if (encodeOverrides.pix_fmt)                 payload.pix_fmt         = encodeOverrides.pix_fmt;
      if (encodeOverrides.encoder_speed)           payload.encoder_speed   = encodeOverrides.encoder_speed;
      if (encodeOverrides.subtitle_mode)           payload.subtitle_mode   = encodeOverrides.subtitle_mode;
      if (encodeOverrides.force_stereo != null)    payload.force_stereo    = encodeOverrides.force_stereo;
      if (encodeOverrides.audio_normalize != null) payload.audio_normalize = encodeOverrides.audio_normalize;
      if (encodeOverrides.output_dir)              payload.output_dir      = encodeOverrides.output_dir;
    }
    await POST('/api/jobs', payload);
    state.selectedIds.clear();
    renderTable();
    openQueuePanel();
    const jobs = await GET('/api/jobs');
    state.jobs = jobs;
    renderQueue();
  } catch (e) {
    alert('Error queuing jobs: ' + e.message);
  }
}

// ---------------------------------------------------------------------------
// Add folder modal
// ---------------------------------------------------------------------------

async function confirmAddFolder() {
  const path = DOM.folderPathInput.value.trim();
  if (!path) {
    showModalError('add-folder-modal', 'Please enter a folder path.');
    return;
  }
  hideModalError('add-folder-modal');
  DOM.confirmAddFolderBtn.disabled = true;
  DOM.confirmAddFolderBtn.textContent = 'Adding…';
  try {
    await POST('/api/folders', { path });
    closeModal('add-folder-modal');
    DOM.folderPathInput.value = '';
    await fetchFolders();
    applyFilters();
  } catch (e) {
    showModalError('add-folder-modal', e.message);
  } finally {
    DOM.confirmAddFolderBtn.disabled = false;
    DOM.confirmAddFolderBtn.textContent = 'Add & Scan';
  }
}

function showModalError(modalId, msg) {
  const el = modalId === 'add-folder-modal' ? DOM.addFolderError : null;
  if (el) { el.textContent = msg; el.classList.remove('hidden'); }
}

function hideModalError(modalId) {
  const el = modalId === 'add-folder-modal' ? DOM.addFolderError : null;
  if (el) el.classList.add('hidden');
}

// ---------------------------------------------------------------------------
// Modal open / close
// ---------------------------------------------------------------------------

const _modalStack = [];

function openModal(id) {
  $(id).classList.remove('hidden');
  _modalStack.push(id);
}

function closeModal(id) {
  $(id).classList.add('hidden');
  const idx = _modalStack.lastIndexOf(id);
  if (idx !== -1) _modalStack.splice(idx, 1);
}

function bindModals() {
  document.querySelectorAll('.modal-close, .btn-cancel').forEach(btn => {
    const modalId = btn.dataset.modal;
    if (modalId) btn.addEventListener('click', () => closeModal(modalId));
  });

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
      if (e.target === overlay) closeModal(overlay.id);
    });
  });

  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _modalStack.length > 0) {
      closeModal(_modalStack[_modalStack.length - 1]);
    }
  });

  DOM.addFolderBtn.addEventListener('click', () => {
    hideModalError('add-folder-modal');
    DOM.folderPathInput.value = '';
    openModal('add-folder-modal');
    setTimeout(() => DOM.folderPathInput.focus(), 50);
  });

  DOM.confirmAddFolderBtn.addEventListener('click', confirmAddFolder);

  DOM.folderPathInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') confirmAddFolder();
  });
}

// ---------------------------------------------------------------------------
// Queue panel
// ---------------------------------------------------------------------------

function openQueuePanel() {
  DOM.queuePanel.classList.add('expanded');
  DOM.queuePanel.classList.remove('collapsed');
}

function bindQueueToggle() {
  DOM.queueToggle.addEventListener('click', () => {
    DOM.queuePanel.classList.toggle('expanded');
    DOM.queuePanel.classList.toggle('collapsed');
  });
}

// ---------------------------------------------------------------------------
// Resizable columns
// ---------------------------------------------------------------------------

function initResizableColumns() {
  const table = document.getElementById('file-table');
  const cols  = table.querySelectorAll('colgroup col');
  const ths   = table.querySelectorAll('thead th');

  ths.forEach((th, i) => {
    cols[i].style.width = th.offsetWidth + 'px';
  });
  loadColumnWidths(cols);

  ths.forEach((th, i) => {
    const handle = th.querySelector('.resize-handle');
    if (!handle) return;

    handle.addEventListener('mousedown', e => {
      e.preventDefault();
      e.stopPropagation();
      const startX = e.clientX;
      const startW = cols[i].offsetWidth;
      handle.classList.add('dragging');

      const onMove = e => {
        const newW = Math.max(40, startW + (e.clientX - startX));
        cols[i].style.width = newW + 'px';
      };
      const onUp = () => {
        handle.classList.remove('dragging');
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        saveColumnWidths(cols);
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });
  });
}

function renderQueue() {
  const jobs = state.jobs;
  const activeJobs = jobs.filter(j => j.status === 'queued' || j.status === 'running');

  if (activeJobs.length > 0) {
    DOM.queueCountBadge.textContent = activeJobs.length;
    DOM.queueCountBadge.classList.remove('hidden');
  } else {
    DOM.queueCountBadge.classList.add('hidden');
  }

  const list = DOM.queueList;
  list.innerHTML = '';

  for (const job of jobs) {
    if (job.status === 'running') continue;
    const row = document.createElement('div');
    row.className = 'queue-job-row';

    const statusDot = `<span class="queue-job-status status-${job.status}"></span>`;
    const name = job.filename || `File #${job.file_id}`;
    const type = job.job_type || 'encode';
    const time = job.finished_at
      ? new Date(job.finished_at + 'Z').toLocaleTimeString()
      : (job.added_at ? new Date(job.added_at + 'Z').toLocaleTimeString() : '');

    const cancelBtn = job.status === 'queued'
      ? `<button class="queue-job-cancel" data-job-id="${job.id}" title="Cancel">&#x2715;</button>`
      : '';

    const errorTip = job.error_msg
      ? `<span class="text-muted" style="font-size:10px;max-width:200px;overflow:hidden;text-overflow:ellipsis;" title="${job.error_msg}">error</span>`
      : '';

    row.innerHTML = `
      ${statusDot}
      <span class="queue-job-name" title="${name}">${name}</span>
      ${errorTip}
      <span class="queue-job-type">${type}</span>
      <span class="queue-job-time">${time}</span>
      ${cancelBtn}
    `;

    if (job.status === 'queued') {
      row.querySelector('.queue-job-cancel').addEventListener('click', async () => {
        try {
          await DELETE(`/api/jobs/${job.id}`);
          state.jobs = await GET('/api/jobs');
          renderQueue();
        } catch (e) {
          alert('Could not cancel: ' + e.message);
        }
      });
    }

    list.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// Flagged panel
// ---------------------------------------------------------------------------

async function fetchFlaggedFiles() {
  try {
    const data = await GET('/api/files?needs_optimize=1&limit=2000&sort=filename&dir=asc');
    state.flaggedFiles = data.files;
    renderFlaggedPanel();
  } catch (e) {
    console.error('fetchFlaggedFiles:', e);
  }
}

function renderFlaggedPanel() {
  const files = state.flaggedFiles;
  const count = files.length;

  if (count > 0) {
    DOM.flaggedCountBadge.textContent = count;
    DOM.flaggedCountBadge.classList.remove('hidden');
  } else {
    DOM.flaggedCountBadge.classList.add('hidden');
  }

  const counts = { hi10p: 0, av1: 0, bitrate: 0 };
  for (const f of files) {
    for (const r of getFlagReasons(f)) counts[r] = (counts[r] || 0) + 1;
  }
  let bdHtml = '';
  if (counts.hi10p)   bdHtml += `<span class="flag-reason-badge flag-reason-hi10p">${counts.hi10p} Hi10P</span>`;
  if (counts.av1)     bdHtml += `<span class="flag-reason-badge flag-reason-av1">${counts.av1} AV1</span>`;
  if (counts.bitrate) bdHtml += `<span class="flag-reason-badge flag-reason-bitrate">${counts.bitrate} High Bitrate</span>`;
  if (count > 0) bdHtml += `<button class="flagged-select-all-btn" id="flagged-select-all-btn">Select All</button>`;
  DOM.flaggedBreakdown.innerHTML = bdHtml;

  if (count > 0) {
    const btn = document.getElementById('flagged-select-all-btn');
    if (btn) btn.addEventListener('click', e => {
      e.stopPropagation();
      files.forEach(f => state.selectedIds.add(f.id));
      renderTable();
      renderFlaggedPanel();
    });
  }

  const list = DOM.flaggedList;
  list.innerHTML = '';
  for (const file of files) {
    const reasons = getFlagReasons(file);
    const row = document.createElement('div');
    row.className = 'flagged-file-row' + (state.selectedIds.has(file.id) ? ' selected-flag' : '');
    const reasonBadges = reasons.map(r => {
      const cls = r === 'hi10p' ? 'flag-reason-hi10p' : r === 'av1' ? 'flag-reason-av1' : 'flag-reason-bitrate';
      const lbl = r === 'hi10p' ? 'Hi10P' : r === 'av1' ? 'AV1' : 'High Bitrate';
      return `<span class="flag-reason-badge ${cls}">${lbl}</span>`;
    }).join('');
    row.innerHTML = `
      <span class="flagged-file-name" title="${file.filename}">${file.filename}</span>
      <span class="flagged-file-reasons">${reasonBadges}</span>
    `;
    row.addEventListener('click', () => {
      if (state.selectedIds.has(file.id)) {
        state.selectedIds.delete(file.id);
      } else {
        state.selectedIds.add(file.id);
      }
      row.classList.toggle('selected-flag', state.selectedIds.has(file.id));
      syncSelectAllCheckbox();
      updateOptimizeBtn();
      renderTable();
    });
    list.appendChild(row);
  }
}

function bindFlaggedToggle() {
  DOM.flaggedToggle.addEventListener('click', () => {
    DOM.flaggedPanel.classList.toggle('expanded');
    DOM.flaggedPanel.classList.toggle('collapsed');
  });
}

// ---------------------------------------------------------------------------
// Persistent state (localStorage)
// ---------------------------------------------------------------------------

const LS_FILTERS = 'mw_filters';
const LS_COLS    = 'mw_col_widths';

function saveFiltersToStorage() {
  localStorage.setItem(LS_FILTERS, JSON.stringify({
    filters: state.filters,
    search: state.search,
    sort: state.sort,
  }));
}

function loadFiltersFromStorage() {
  try {
    const raw = localStorage.getItem(LS_FILTERS);
    if (!raw) return;
    const saved = JSON.parse(raw);
    if (saved.filters) Object.assign(state.filters, saved.filters);
    if (saved.search)  state.search = saved.search;
    if (saved.sort)    Object.assign(state.sort, saved.sort);

    DOM.filterFolder.value      = state.filters.folder_id;
    DOM.filterRes.value         = state.filters.resolution;
    DOM.filterCodec.value       = state.filters.codec;
    DOM.filterHdr.value         = state.filters.hdr;
    DOM.filterLang.value        = state.filters.audio_lang;
    DOM.filterAudioCodec.value  = state.filters.audio_codec;
    DOM.filterOpt.value         = state.filters.needs_optimize;
    DOM.searchInput.value       = state.search;
    updateSortArrows();
  } catch {}
}

function saveColumnWidths(cols) {
  const widths = Array.from(cols).map(c => c.style.width);
  localStorage.setItem(LS_COLS, JSON.stringify(widths));
}

function loadColumnWidths(cols) {
  try {
    const raw = localStorage.getItem(LS_COLS);
    if (!raw) return;
    const widths = JSON.parse(raw);
    widths.forEach((w, i) => { if (cols[i] && w) cols[i].style.width = w; });
  } catch {}
}

// ---------------------------------------------------------------------------
// File detail drawer
// ---------------------------------------------------------------------------

function openFileDetail(file) {
  state.openFileId = file.id;
  DOM.drawerFilename.textContent = file.filename;
  DOM.drawerBody.innerHTML = renderFileDetailHtml(file);

  if (file.needs_optimize) {
    DOM.drawerOptimizeBtn.classList.remove('hidden');
    DOM.drawerOptimizeBtn.onclick = () => {
      state.selectedIds.add(file.id);
      closeFileDetail();
      handleOptimize();
    };
  } else {
    DOM.drawerOptimizeBtn.classList.add('hidden');
  }

  DOM.fileDetailDrawer.classList.add('open');
}

function closeFileDetail() {
  DOM.fileDetailDrawer.classList.remove('open');
  state.openFileId = null;
}

function renderFileDetailHtml(file) {
  const row = (label, value, cls = '') =>
    `<div class="detail-row"><span class="detail-label">${label}</span><span class="detail-value ${cls}">${value || '—'}</span></div>`;

  let html = '';

  html += `<div class="detail-section"><div class="detail-section-title">File</div>`;
  html += row('Path', file.path || file.folder_path, 'path');
  html += row('Size', fmtSize(file.size_bytes));
  html += row('Duration', fmtDuration(file.duration_s));
  html += row('Bitrate', fmtBitrate(file.bitrate_kbps));
  html += `</div>`;

  html += `<div class="detail-section"><div class="detail-section-title">Video</div>`;
  html += row('Codec', codecLabel(file.video_codec));
  html += row('Profile', file.video_profile);
  html += row('Resolution', fmtResolution(file.width, file.height));
  html += row('Pixel Format', file.pix_fmt);
  html += row('HDR', file.hdr_type ? hdrBadgeHtml(file.hdr_type) : 'SDR');
  html += row('Color Space', file.color_space);
  html += row('Transfer', file.color_transfer);
  html += `</div>`;

  try {
    const tracks = JSON.parse(file.audio_tracks || '[]');
    if (tracks.length > 0) {
      html += `<div class="detail-section"><div class="detail-section-title">Audio (${tracks.length})</div>`;
      for (const t of tracks) {
        const lang = langLabel(t.language || '');
        const codec = audioTrackLabel(t);
        const ch = fmtChannels(t.channels);
        const sr = t.sample_rate ? `${Math.round(t.sample_rate / 1000)}kHz` : '';
        html += `<div class="detail-track">
          <span class="${langBadgeClass(t.language || '')}">${lang}</span>
          <span class="audio-track-codec">${codec}</span>
          <span class="detail-track-info">${[ch, sr].filter(Boolean).join(' · ')}</span>
        </div>`;
      }
      html += `</div>`;
    }
  } catch {}

  try {
    const subs = JSON.parse(file.subtitle_tracks || '[]');
    if (subs.length > 0) {
      html += `<div class="detail-section"><div class="detail-section-title">Subtitles (${subs.length})</div>`;
      for (const s of subs) {
        html += `<div class="detail-track">
          <span class="${langBadgeClass(s.language || '')}">${langLabel(s.language || '')}</span>
          <span class="detail-track-info">${s.codec_name || ''}</span>
        </div>`;
      }
      html += `</div>`;
    }
  } catch {}

  html += `<div class="detail-section"><div class="detail-section-title">Other</div>`;
  html += row('Attachments', file.has_attachments ? 'Yes (fonts/covers)' : 'None');
  html += row('Scanned', file.scanned_at ? new Date(file.scanned_at + 'Z').toLocaleString() : '—');
  html += `</div>`;

  return html;
}

// ---------------------------------------------------------------------------
// Queue panel tabs
// ---------------------------------------------------------------------------

function switchQueueTab(tab) {
  state.activeQueueTab = tab;
  document.querySelectorAll('.queue-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.queue-tab-content').forEach(div => {
    div.classList.toggle('active', div.id === `queue-tab-${tab}`);
  });
  if (tab === 'log') renderLog();
  if (tab === 'history') renderHistory();
}

function bindQueueTabs() {
  document.querySelectorAll('.queue-tab').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      switchQueueTab(btn.dataset.tab);
    });
  });
}

// ---------------------------------------------------------------------------
// Encode log
// ---------------------------------------------------------------------------

async function fetchLog() {
  try {
    const data = await GET('/api/jobs/log');
    state.logLines = data.lines || [];
    if (state.activeQueueTab === 'log') renderLog();
  } catch {}
}

function renderLog() {
  const el = DOM.encodeLog;
  if (state.logLines.length === 0) {
    el.textContent = state.currentProgress && state.currentProgress.status === 'running'
      ? 'Waiting for log output…'
      : 'No encode running.';
    return;
  }
  el.textContent = state.logLines.join('\n');
  el.scrollTop = el.scrollHeight;
}

function startLogPolling() {
  if (state._logPollTimer) return;
  state._logPollTimer = setInterval(fetchLog, 1500);
}

function stopLogPolling() {
  if (state._logPollTimer) {
    clearInterval(state._logPollTimer);
    state._logPollTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Encode history
// ---------------------------------------------------------------------------

function renderHistory() {
  const list = DOM.historyList;
  const finished = state.jobs.filter(j => j.status === 'done' || j.status === 'error');
  list.innerHTML = '';

  if (finished.length === 0) {
    list.innerHTML = '<div style="padding:12px;font-size:12px;color:var(--text-muted);text-align:center;">No completed encodes yet.</div>';
    return;
  }

  for (const job of [...finished].reverse()) {
    const row = document.createElement('div');
    row.className = 'history-job-row';

    const dot = `<span class="queue-job-status status-${job.status}"></span>`;
    const name = job.filename || `File #${job.file_id}`;
    const type = job.job_type || 'encode';

    let duration = '';
    if (job.started_at && job.finished_at) {
      const s = (new Date(job.finished_at + 'Z') - new Date(job.started_at + 'Z')) / 1000;
      duration = fmtDuration(s);
    }

    const time = job.finished_at
      ? new Date(job.finished_at + 'Z').toLocaleString()
      : '';

    const errHtml = job.error_msg
      ? `<span class="history-job-error" title="${job.error_msg}">${job.error_msg}</span>`
      : '';

    row.innerHTML = `
      ${dot}
      <span class="history-job-name" title="${name}">${name}</span>
      ${errHtml}
      <span class="queue-job-type">${type}</span>
      <span class="history-job-meta">${duration ? duration + ' · ' : ''}${time}</span>
    `;
    list.appendChild(row);
  }
}

// ---------------------------------------------------------------------------
// SSE progress
// ---------------------------------------------------------------------------

function connectSSE() {
  const es = new EventSource('/api/jobs/progress');

  es.addEventListener('progress', e => {
    try {
      const p = JSON.parse(e.data);
      state.currentProgress = p;
      renderProgress(p);
    } catch {}
  });

  es.addEventListener('queue', e => {
    try {
      const q = JSON.parse(e.data);
      state.jobs = q;
      renderQueue();
    } catch {}
  });

  es.addEventListener('done', e => {
    renderProgress(null);
    fetchFolders();
    fetchFiles();
    fetchFlaggedFiles();
  });

  es.addEventListener('error', e => {
    if (es.readyState === EventSource.CLOSED) {
      setTimeout(connectSSE, 3000);
    }
  });

  setInterval(async () => {
    try {
      const jobs = await GET('/api/jobs');
      state.jobs = jobs;
      renderQueue();
    } catch {}
  }, 2000);
}

function renderProgress(p) {
  if (!p || p.status === 'idle' || p.status === 'done') {
    DOM.progressSection.classList.add('hidden');
    return;
  }

  DOM.progressSection.classList.remove('hidden');
  DOM.progressFilename.textContent = p.filename || '—';
  DOM.progressBadge.textContent = p.job_type || 'encode';
  DOM.progressFill.style.width = (p.percent || 0) + '%';
  DOM.progressPercent.textContent = (p.percent || 0).toFixed(1) + '%';
  DOM.progressFps.textContent = (p.fps || 0).toFixed(1) + ' fps';
  DOM.progressSpeed.textContent = p.speed || '0x';
  DOM.progressEta.textContent = 'ETA ' + fmtEta(p.eta_s);

  if (p.status === 'running' && !DOM.queuePanel.classList.contains('expanded')) {
    openQueuePanel();
  }

  if (p.status === 'running') {
    startLogPolling();
  } else {
    stopLogPolling();
    fetchLog();
  }
}

// ---------------------------------------------------------------------------
// Scan status polling
// ---------------------------------------------------------------------------

let scanPollTimer = null;

async function pollScanStatus() {
  try {
    const status = await GET('/api/scan/status');
    state.scanStatus = status;

    if (status.scanning) {
      DOM.scanIndicator.classList.remove('hidden');
      DOM.scanIdle.classList.add('hidden');
      const queued = status.queued || 0;
      const queuedSuffix = queued > 0 ? ` (+${queued} queued)` : '';
      DOM.scanLabel.textContent = status.current_file
        ? `Scanning ${status.scanned}/${status.total} — ${status.current_file}${queuedSuffix}`
        : `Scanning…${queuedSuffix}`;

      if (!scanPollTimer) {
        scanPollTimer = setInterval(pollScanStatus, 2000);
      }
    } else if ((status.queued || 0) > 0) {
      // Scans are queued but briefly idle between jobs — keep indicator visible
      DOM.scanIndicator.classList.remove('hidden');
      DOM.scanIdle.classList.add('hidden');
      DOM.scanLabel.textContent = `Starting next scan… (${status.queued} queued)`;
    } else {
      DOM.scanIndicator.classList.add('hidden');
      DOM.scanIdle.classList.remove('hidden');

      if (scanPollTimer) {
        clearInterval(scanPollTimer);
        scanPollTimer = null;
        await fetchFolders();
        applyFilters();
        fetchFlaggedFiles();
      }
    }
  } catch {}
}

// ---------------------------------------------------------------------------
// Settings modal
// ---------------------------------------------------------------------------

function _langChipSetDisabled(disabled) {
  if (disabled) {
    DOM.settingsLangChips.classList.add('disabled');
  } else {
    DOM.settingsLangChips.classList.remove('disabled');
  }
  DOM.settingsLangChips.querySelectorAll('input').forEach(cb => {
    cb.disabled = disabled;
  });
}

function _syncLangChipClasses() {
  DOM.settingsLangChips.querySelectorAll('label.lang-chip').forEach(lbl => {
    const cb = lbl.querySelector('input');
    lbl.classList.toggle('active', cb.checked);
  });
}

function _loadLangChips(languages) {
  const keepAll = !languages || languages.length === 0;
  DOM.settingsLangAll.checked = keepAll;
  DOM.settingsLangChips.querySelectorAll('input').forEach(cb => {
    cb.checked = !keepAll && languages.includes(cb.value);
  });
  _langChipSetDisabled(keepAll);
  _syncLangChipClasses();
}

function _getSelectedLanguages() {
  if (DOM.settingsLangAll.checked) return [];
  const langs = [];
  DOM.settingsLangChips.querySelectorAll('input:checked').forEach(cb => langs.push(cb.value));
  return langs;
}

async function openSettingsModal() {
  DOM.settingsError.classList.add('hidden');
  DOM.settingsSuccess.classList.add('hidden');
  DOM.settingsRestartNote.classList.add('hidden');
  switchSettingsTab('encoder');
  try {
    const s = await GET('/api/settings');
    DOM.settingsHwEncoder.value = s.hw_encoder || 'nvenc';
    DOM.settingsVaapiDevice.value = s.vaapi_device || '';
    DOM.settingsFfmpeg.value    = s.ffmpeg_path || '';
    DOM.settingsFfprobe.value   = s.ffprobe_path || '';

    const codec = s.output_video_codec || 'hevc';
    DOM.settingsOutputCodec.querySelectorAll('input[type="radio"]').forEach(r => {
      r.checked = r.value === codec;
    });

    const cq = s.video_quality_cq ?? 24;
    DOM.settingsCq.value = cq;
    DOM.settingsCqDisplay.textContent = cq;

    DOM.settingsOutputContainer.value = s.output_container || 'mkv';
    DOM.settingsScaleHeight.value     = s.scale_height ? String(s.scale_height) : '0';
    DOM.settingsPixFmt.value          = s.pix_fmt || 'auto';
    DOM.settingsEncoderSpeed.value    = s.encoder_speed || 'medium';
    DOM.settingsSubtitleMode.value    = s.subtitle_mode || 'copy';

    DOM.settingsAudioAction.value = s.audio_lossy_action || 'opus';

    _loadLangChips(s.audio_languages);

    DOM.settingsForceStereo.checked    = s.force_stereo || false;
    DOM.settingsAudioNormalize.checked = s.audio_normalize || false;

    DOM.settingsThreshold.value = s.needs_optimize_bitrate_threshold_kbps || '';
    state.bitrateThreshold = s.needs_optimize_bitrate_threshold_kbps || 25000;
    DOM.settingsFlagAv1.checked = s.flag_av1 !== false;

    DOM.settingsWebUiEnabled.checked = s.web_ui_enabled || false;
    DOM.settingsWebUiHost.value      = s.web_ui_host || '0.0.0.0';
    DOM.settingsWebUiPort.value      = s.web_ui_port || 8000;
    DOM.settingsWebUiUsername.value  = localStorage.getItem('settings-web-ui-username') || '';
    DOM.settingsWebUiPassword.value  = localStorage.getItem('settings-web-ui-password') || '';
    // Snapshot network settings so saveSettings can detect changes
    state._loadedNetworkSettings = {
      enabled:  s.web_ui_enabled || false,
      host:     s.web_ui_host || '0.0.0.0',
      port:     s.web_ui_port || 8000,
      username: localStorage.getItem('settings-web-ui-username') || '',
      password: localStorage.getItem('settings-web-ui-password') || '',
    };
    _updateNetworkFieldVisibility();
  } catch (e) {
    DOM.settingsError.textContent = 'Failed to load settings: ' + e.message;
    DOM.settingsError.classList.remove('hidden');
  }
  openModal('settings-modal');
}

function _updateNetworkFieldVisibility() {
  DOM.settingsNetworkFields.style.display = DOM.settingsWebUiEnabled.checked ? '' : 'none';
}

async function saveSettings() {
  DOM.settingsError.classList.add('hidden');
  DOM.settingsSuccess.classList.add('hidden');
  DOM.settingsSaveBtn.disabled = true;

  const threshold = parseInt(DOM.settingsThreshold.value, 10);
  if (DOM.settingsThreshold.value && (isNaN(threshold) || threshold < 1000)) {
    DOM.settingsError.textContent = 'Threshold must be at least 1000 kbps.';
    DOM.settingsError.classList.remove('hidden');
    DOM.settingsSaveBtn.disabled = false;
    return;
  }

  const selectedCodec = DOM.settingsOutputCodec.querySelector('input[type="radio"]:checked');

  const selectedContainer = DOM.settingsOutputContainer.value;
  const selectedCodecVal  = selectedCodec?.value;
  if (selectedCodecVal === 'vp9' && selectedContainer === 'mp4') {
    DOM.settingsError.textContent = 'VP9 is not compatible with the MP4 container. Use MKV or WebM.';
    DOM.settingsError.classList.remove('hidden');
    DOM.settingsSaveBtn.disabled = false;
    return;
  }
  if (selectedContainer === 'webm' && selectedCodecVal && !['vp9', 'av1'].includes(selectedCodecVal)) {
    DOM.settingsError.textContent = 'WebM only supports VP9 and AV1. Use MKV for H.264 or HEVC.';
    DOM.settingsError.classList.remove('hidden');
    DOM.settingsSaveBtn.disabled = false;
    return;
  }

  const webUiPort = parseInt(DOM.settingsWebUiPort.value, 10);
  const webUiUsername = DOM.settingsWebUiUsername.value.trim();
  const webUiPassword = DOM.settingsWebUiPassword.value;

  try {
    const scaleHeightRaw = parseInt(DOM.settingsScaleHeight.value, 10);
    await POST('/api/settings', {
      hw_encoder:          DOM.settingsHwEncoder.value || null,
      vaapi_device:        DOM.settingsVaapiDevice.value.trim() || null,
      ffmpeg_path:         DOM.settingsFfmpeg.value.trim() || null,
      ffprobe_path:        DOM.settingsFfprobe.value.trim() || null,
      output_video_codec:  selectedCodec ? selectedCodec.value : null,
      video_quality_cq:    parseInt(DOM.settingsCq.value, 10),
      output_container:    DOM.settingsOutputContainer.value || null,
      scale_height:        isNaN(scaleHeightRaw) ? null : scaleHeightRaw,
      pix_fmt:             DOM.settingsPixFmt.value || null,
      encoder_speed:       DOM.settingsEncoderSpeed.value || null,
      subtitle_mode:       DOM.settingsSubtitleMode.value || null,
      audio_lossy_action:  DOM.settingsAudioAction.value || null,
      audio_languages:     _getSelectedLanguages(),
      force_stereo:        DOM.settingsForceStereo.checked,
      audio_normalize:     DOM.settingsAudioNormalize.checked,
      needs_optimize_bitrate_threshold_kbps: DOM.settingsThreshold.value ? threshold : null,
      flag_av1:            DOM.settingsFlagAv1.checked,
      web_ui_enabled:      DOM.settingsWebUiEnabled.checked,
      web_ui_host:         DOM.settingsWebUiHost.value.trim() || null,
      web_ui_port:         isNaN(webUiPort) ? null : webUiPort,
      web_ui_username:     webUiUsername || null,
      web_ui_password:     webUiPassword || null,
    });

    if (webUiUsername && webUiPassword) {
      localStorage.setItem('settings-web-ui-username', webUiUsername);
      localStorage.setItem('settings-web-ui-password', webUiPassword);
    } else {
      localStorage.removeItem('settings-web-ui-username');
      localStorage.removeItem('settings-web-ui-password');
    }

    // Detect if any network settings actually changed
    const prev = state._loadedNetworkSettings || {};
    const networkChanged = DOM.settingsWebUiEnabled.checked !== prev.enabled
      || DOM.settingsWebUiHost.value.trim()   !== prev.host
      || String(isNaN(webUiPort) ? prev.port : webUiPort) !== String(prev.port)
      || webUiUsername !== prev.username
      || webUiPassword !== prev.password;

    if (!isNaN(threshold)) state.bitrateThreshold = threshold;
    fetchFlaggedFiles();
    fetchFiles();
    DOM.settingsSuccess.classList.remove('hidden');
    setTimeout(() => DOM.settingsSuccess.classList.add('hidden'), 3000);
    if (networkChanged) {
      DOM.settingsRestartNote.classList.remove('hidden');
      // Don't auto-hide — user must see this and restart
    } else {
      DOM.settingsRestartNote.classList.add('hidden');
    }
  } catch (e) {
    DOM.settingsError.textContent = 'Save failed: ' + e.message;
    DOM.settingsError.classList.remove('hidden');
  } finally {
    DOM.settingsSaveBtn.disabled = false;
  }
}

function switchSettingsTab(tab) {
  document.querySelectorAll('.settings-tab').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.stab === tab);
  });
  document.querySelectorAll('.settings-tab-content').forEach(div => {
    div.classList.toggle('active', div.id === `stab-${tab}`);
  });
  if (tab === 'database') loadOptimizedFiles();
  if (tab === 'presets')  loadPresetsTab();
}

async function loadOptimizedFiles() {
  const list = $('db-optimized-list');
  const reflagAllBtn = $('db-reflag-all-btn');
  list.innerHTML = '<div class="db-empty db-loading">Loading…</div>';
  try {
    const files = await GET('/api/optimized-files');
    if (files.length === 0) {
      list.innerHTML = '<div class="db-empty">No optimized files yet.</div>';
      reflagAllBtn.style.display = 'none';
      return;
    }
    reflagAllBtn.style.display = '';
    list.innerHTML = '';
    for (const f of files) {
      const row = document.createElement('div');
      row.className = 'db-file-row';
      row.dataset.fileId = f.id;
      const date = f.last_optimized_at ? f.last_optimized_at.replace('T', ' ').slice(0, 16) : '—';
      const flagged = f.needs_optimize === 1;
      row.innerHTML = `
        <div class="db-file-info">
          <span class="db-file-name" title="${escHtml(f.path)}">${escHtml(f.filename)}</span>
          <span class="db-file-meta">${f.video_codec?.toUpperCase() ?? '—'} · ${f.bitrate_kbps ? Math.round(f.bitrate_kbps / 1000) + ' Mbps' : '—'} · ${f.last_job_type} · ${date}</span>
        </div>
        <button class="btn-db-reflag ${flagged ? 'btn-db-reflag-active' : ''}" data-file-id="${f.id}" ${flagged ? 'disabled' : ''}>
          ${flagged ? 'Flagged' : 'Re-flag'}
        </button>`;
      list.appendChild(row);
    }
    list.querySelectorAll('.btn-db-reflag:not([disabled])').forEach(btn => {
      btn.addEventListener('click', () => reflagFile(parseInt(btn.dataset.fileId, 10), btn));
    });
  } catch (e) {
    list.innerHTML = `<div class="db-empty db-error">Failed to load: ${e.message}</div>`;
    reflagAllBtn.style.display = 'none';
  }
}

async function reflagFile(fileId, btn) {
  if (btn) { btn.disabled = true; btn.textContent = '…'; }
  try {
    await POST(`/api/files/${fileId}/reflag`, {});
    if (btn) { btn.textContent = 'Flagged'; btn.classList.add('btn-db-reflag-active'); }
    const f = state.files.find(f => f.id === fileId);
    if (f) { f.needs_optimize = 1; renderTable(); }
    fetchFlaggedFiles();
  } catch (e) {
    if (btn) { btn.disabled = false; btn.textContent = 'Re-flag'; }
    console.error('reflag failed', e);
  }
}

async function reflagAllOptimized() {
  const btns = document.querySelectorAll('#db-optimized-list .btn-db-reflag:not([disabled])');
  for (const btn of btns) {
    await reflagFile(parseInt(btn.dataset.fileId, 10), btn);
  }
}

function bindSettingsModal() {
  DOM.settingsBtn.addEventListener('click', openSettingsModal);
  DOM.settingsSaveBtn.addEventListener('click', saveSettings);

  document.querySelectorAll('.settings-tab').forEach(btn => {
    btn.addEventListener('click', () => switchSettingsTab(btn.dataset.stab));
  });

  DOM.settingsCq.addEventListener('input', () => {
    DOM.settingsCqDisplay.textContent = DOM.settingsCq.value;
  });

  DOM.settingsWebUiEnabled.addEventListener('change', _updateNetworkFieldVisibility);

  DOM.settingsLangAll.addEventListener('change', () => {
    _langChipSetDisabled(DOM.settingsLangAll.checked);
    _syncLangChipClasses();
  });

  DOM.settingsLangChips.querySelectorAll('input').forEach(cb => {
    cb.addEventListener('change', _syncLangChipClasses);
  });
}

// ---------------------------------------------------------------------------
// About modal
// ---------------------------------------------------------------------------

const _ABOUT_HW_NAMES  = { nvenc: 'NVIDIA NVENC', qsv: 'Intel Quick Sync', amf: 'AMD AMF', vaapi: 'VA-API', software: 'Software (CPU)' };
const _ABOUT_CODEC_NAMES = { hevc: 'HEVC (H.265)', av1: 'AV1', h264: 'H.264 (AVC)', vp9: 'VP9' };
const _ABOUT_FFMPEG_ENC = {
  nvenc:    { hevc: 'hevc_nvenc',  av1: 'av1_nvenc',  h264: 'h264_nvenc', vp9: 'libvpx-vp9' },
  qsv:      { hevc: 'hevc_qsv',   av1: 'av1_qsv',    h264: 'h264_qsv',   vp9: 'libvpx-vp9' },
  amf:      { hevc: 'hevc_amf',   av1: 'av1_amf',    h264: 'h264_amf',   vp9: 'libvpx-vp9' },
  vaapi:    { hevc: 'hevc_vaapi', av1: 'av1_vaapi',   h264: 'h264_vaapi', vp9: 'libvpx-vp9' },
  software: { hevc: 'libx265',    av1: 'libsvtav1',   h264: 'libx264',    vp9: 'libvpx-vp9' },
};
const _ABOUT_LANG_NAMES = {
  eng: 'English', jpn: 'Japanese', fre: 'French',    ger: 'German',
  spa: 'Spanish', chi: 'Chinese',  ita: 'Italian',   por: 'Portuguese',
  kor: 'Korean',  rus: 'Russian',  ara: 'Arabic',    hin: 'Hindi',
};

function renderAboutHtml(s) {
  const hw           = s.hw_encoder          || 'nvenc';
  const codec        = s.output_video_codec  || 'hevc';
  const cq           = s.video_quality_cq    ?? 24;
  const audioAct     = s.audio_lossy_action  || 'opus';
  const langs        = s.audio_languages     || [];
  const flagAv1      = s.flag_av1            !== false;
  const threshold    = s.needs_optimize_bitrate_threshold_kbps || 25000;
  const container    = s.output_container    || 'mkv';
  const scaleHeight  = s.scale_height        || null;
  const pixFmt       = s.pix_fmt             || 'auto';
  const encSpeed     = s.encoder_speed       || 'medium';
  const forceStereo  = !!s.force_stereo;
  const normalize    = !!s.audio_normalize;
  const subtitleMode = s.subtitle_mode       || 'copy';

  const hwName    = _ABOUT_HW_NAMES[hw]   || hw.toUpperCase();
  const codecName = _ABOUT_CODEC_NAMES[codec] || codec.toUpperCase();
  const ffEnc     = (_ABOUT_FFMPEG_ENC[hw] || {})[codec] || `${codec}_${hw}`;

  const langLabel = langs.length === 0
    ? 'all languages'
    : langs.map(l => _ABOUT_LANG_NAMES[l] || l.toUpperCase()).join(', ');

  const qualDesc = codec === 'vp9'   ? `CQ ${cq} (libvpx-vp9 — CPU encode regardless of hardware setting)`
                 : hw === 'nvenc'    ? `VBR CQ ${cq}, preset p4`
                 : hw === 'qsv'      ? `global_quality ${cq}, look-ahead enabled`
                 : hw === 'software' ? `CRF ${cq}`
                 :                     `CQP ${cq}, balanced preset`;

  const scaleDesc    = scaleHeight ? `downscaled to <strong>${scaleHeight}p</strong> (aspect preserved)` : 'original resolution';
  const pixFmtDesc   = pixFmt !== 'auto' ? `, forced pixel format <code>${pixFmt}</code>` : '';
  const speedDesc    = `, encoder speed <strong>${encSpeed}</strong>`;
  const containerDesc = container === 'mp4'  ? 'MP4 (AAC audio, no subtitles)'
                      : container === 'webm' ? 'WebM'
                      :                        'MKV';

  const outputDesc = `Encoded to a temporary <code>.new.${container}</code> alongside the original by default. On success the original is deleted and the new file takes its place. If an output directory is set via the Encode modal, the file is written directly to that directory and the original is always kept.`;

  const audioLossyVal = audioAct === 'copy'
    ? 'All audio tracks are <strong>copied without re-encoding</strong> regardless of codec.'
    : audioAct === 'aac'
    ? 'EAC3, AC3, DTS, AAC, and MP3 tracks are re-encoded to <strong>AAC</strong> — 256 kbps for 5.1/7.1, 160 kbps for stereo, 96 kbps for mono.'
    : 'EAC3, AC3, DTS, AAC, and MP3 tracks are re-encoded to <strong>Opus</strong> — 320 kbps for 5.1/7.1, 192 kbps for stereo, 96 kbps for mono. Smaller than AC3/EAC3 at equivalent or better quality.';

  const av1Style  = flagAv1 ? '' : 'opacity:0.45';
  const av1Status = flagAv1 ? '' : ' <em style="color:var(--text-muted)">(currently disabled — AV1 files will not be flagged)</em>';

  const row = (label, value) => `
    <div class="about-detail-row">
      <span class="about-detail-label">${label}</span>
      <span class="about-detail-value">${value}</span>
    </div>`;

  const flagRow = (badgeCls, badgeText, desc, style = '') => `
    <div class="about-flag-row" style="${style}">
      <span class="flag-reason-badge ${badgeCls}">${badgeText}</span>
      <span class="about-flag-desc">${desc}</span>
    </div>`;

  return `
    <div class="about-section">
      <div class="about-section-title">What is Conduit?</div>
      <p class="about-text">Conduit scans your media folders, extracts technical metadata from every video file using <strong>ffprobe</strong>, and surfaces files that would benefit from re-encoding. It then encodes selected files with <strong>ffmpeg</strong> using <strong>${hwName}</strong> (<code>${ffEnc}</code>), replacing originals in-place. The <strong>Encode</strong> button lets you queue any files with custom per-batch settings and a chosen output directory. <strong>Presets</strong> let you save and reuse encode configurations — a built-in <em>Tower Unite</em> preset (VP9/WebM) is included.</p>
    </div>

    <div class="about-section">
      <div class="about-section-title">Why a File Gets Flagged</div>
      ${flagRow('flag-reason-hi10p', 'Hi10P',
        '<strong>H.264 10-bit</strong> — Hi10P H.264 lacks broad hardware decode support. Most GPUs fall back to software decode, causing high CPU load during playback.')}
      ${flagRow('flag-reason-av1', 'AV1',
        `<strong>AV1</strong> — AV1 hardware decode requires newer hardware (NVIDIA RTX 30xx+, Intel Arc / 12th gen+, AMD RX 6000+). Older hardware falls back to software decode. Re-encoding to ${codecName} gives broader compatibility.${av1Status}`,
        av1Style)}
      ${flagRow('flag-reason-bitrate', 'High Bitrate',
        `<strong>Bitrate above ${(threshold / 1000).toFixed(0)} Mbps</strong> — Files that can likely be re-encoded with significant size savings while maintaining the same visual quality.`)}
    </div>

    <div class="about-section">
      <div class="about-section-title">How Optimization Works</div>
      ${row('Video', `Re-encoded to <strong>${codecName}</strong> using <code>${ffEnc}</code> (${hwName}). ${qualDesc}${speedDesc}${pixFmtDesc}, ${scaleDesc}, main10 profile — preserves 10-bit content and HDR10 color metadata.`)}
      ${row('Container', `Output written as <strong>${containerDesc}</strong>. MP4 forces AAC audio and drops subtitles. WebM requires VP9.`)}
      ${row('Audio (lossy)', audioLossyVal)}
      ${row('Audio (lossless)', 'TrueHD, DTS-HD MA, FLAC, and PCM tracks are <strong>copied without re-encoding</strong> to avoid any quality loss.')}
      ${forceStereo ? row('Force Stereo', 'All audio tracks are <strong>downmixed to stereo (2.0)</strong>.') : ''}
      ${normalize   ? row('Normalization', 'EBU R128 loudness normalization applied — target <strong>−23 LUFS</strong>, true peak <strong>−2 dBTP</strong>.') : ''}
      ${row('Subtitles', subtitleMode === 'strip' ? 'All subtitle tracks are <strong>stripped</strong>.' : 'Subtitle tracks are <strong>copied</strong> (pass-through, filtered by language).')}
      ${row('Track Selection', `Keeping <strong>${langLabel}</strong>. If no matching track is found, the first audio track is kept as a fallback. Applies to subtitles too. DVB teletext/subtitle tracks are always dropped.`)}
      ${row('Output', outputDesc)}
    </div>

    <div class="about-section">
      <div class="about-section-title">HDR Handling</div>
      ${row('HDR10', `Fully preserved through ${codecName} re-encoding. Color space, transfer function, and mastering display metadata are passed through regardless of which hardware encoder is used.`)}
      ${row('HDR10+ / Dolby Vision', `Dynamic HDR metadata <strong>cannot survive re-encoding</strong> on any hardware encoder. You are prompted to choose: <em>Remux</em> (copy video stream, preserve all metadata, re-encode audio only) or <em>Re-encode</em> (full ${codecName} encode, dynamic HDR is lost, falls back to HDR10 or SDR). This prompt also appears when using the Encode button.`)}
      ${row('Remux', 'The video stream is copied byte-for-byte with no quality loss and no GPU required. Only audio is re-encoded. Fastest option — useful when the file is already in a good codec but has large or lossy audio tracks.')}
    </div>`;
}

function bindAboutModal() {
  DOM.aboutBtn.addEventListener('click', async () => {
    const body = $('about-body');
    body.innerHTML = '<div style="padding:20px;font-size:13px;color:var(--text-muted)">Loading…</div>';
    openModal('about-modal');
    try {
      const s = await GET('/api/settings');
      body.innerHTML = renderAboutHtml(s);
    } catch {
      body.innerHTML = renderAboutHtml({});
    }
  });
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', async () => {
  initDOM();

  DOM.hdrRemuxBtn.addEventListener('click', () => {
    closeModal('hdr-modal');
    const ko  = state._pendingKeepOriginal;
    const ov  = state._pendingEncodeOverrides || null;
    const jobs = [];
    if (state._pendingHdrFileIds.length > 0) {
      jobs.push(submitJobs(state._pendingHdrFileIds, 'remux', ko, ov));
    }
    if (state._pendingNonHdrFileIds.length > 0) {
      jobs.push(submitJobs(state._pendingNonHdrFileIds, 'encode', ko, ov));
    }
    Promise.all(jobs);
    state._pendingHdrFileIds = [];
    state._pendingNonHdrFileIds = [];
    state._pendingEncodeOverrides = null;
  });

  DOM.hdrReencodeBtn.addEventListener('click', () => {
    closeModal('hdr-modal');
    const allIds = [...state._pendingHdrFileIds, ...state._pendingNonHdrFileIds];
    const ov = state._pendingEncodeOverrides || null;
    submitJobs(allIds, 'encode', state._pendingKeepOriginal, ov);
    state._pendingHdrFileIds = [];
    state._pendingNonHdrFileIds = [];
    state._pendingEncodeOverrides = null;
  });

  DOM.optimizeReplaceBtn.addEventListener('click', () => {
    closeModal('optimize-confirm-modal');
    state._pendingKeepOriginal = false;
    if (state._pendingHdrFileIds.length > 0) {
      showHdrModal(state.files.filter(f => state._pendingHdrFileIds.includes(f.id)));
    } else {
      submitJobs(state._pendingNonHdrFileIds, 'encode', false);
      state._pendingNonHdrFileIds = [];
    }
  });

  DOM.optimizeKeepBtn.addEventListener('click', () => {
    closeModal('optimize-confirm-modal');
    state._pendingKeepOriginal = true;
    if (state._pendingHdrFileIds.length > 0) {
      showHdrModal(state.files.filter(f => state._pendingHdrFileIds.includes(f.id)));
    } else {
      submitJobs(state._pendingNonHdrFileIds, 'encode', true);
      state._pendingNonHdrFileIds = [];
    }
  });

  document.addEventListener('click', e => {
    if (!e.target.closest('#flag-popover') && !e.target.closest('.flag-popover-trigger')) {
      hideFlagPopover();
    }
  });

  $('db-reflag-all-btn').addEventListener('click', reflagAllOptimized);

  bindModals();
  bindSettingsModal();
  bindAboutModal();
  bindFilters();
  bindSortHeaders();
  bindSelectAll();
  bindQueueToggle();
  bindQueueTabs();
  bindFlaggedToggle();

  $('sidebar-toggle').addEventListener('click', () => {
    $('sidebar').classList.toggle('collapsed');
  });

  DOM.drawerClose.addEventListener('click', closeFileDetail);
  DOM.optimizeBtn.addEventListener('click', handleOptimize);
  DOM.encodeBtn.addEventListener('click', handleCustomEncode);

  DOM.ceCq.addEventListener('input', () => { DOM.ceCqDisplay.textContent = DOM.ceCq.value; });
  DOM.ceReplaceBtn.addEventListener('click', () => _ceSetKeepOriginal(false));
  DOM.ceKeepBtn.addEventListener('click', () => _ceSetKeepOriginal(true));
  DOM.ceHdrRemuxBtn.addEventListener('click', () => _ceSetHdrAction('remux'));
  DOM.ceHdrReencodeBtn.addEventListener('click', () => _ceSetHdrAction('reencode'));
  DOM.ceSubmitBtn.addEventListener('click', _submitCustomEncode);

  DOM.ceBrowseBtn.addEventListener('click', async () => {
    if (window.pywebview?.api?.pick_folder) {
      const dir = await window.pywebview.api.pick_folder();
      if (dir) _ceSetOutputDir(dir);
    } else {
      const dir = prompt('Enter output folder path:');
      if (dir?.trim()) _ceSetOutputDir(dir.trim());
    }
  });

  DOM.ceClearDirBtn.addEventListener('click', () => _ceSetOutputDir(null));

  DOM.cePreset.addEventListener('change', () => {
    const id = DOM.cePreset.value;
    if (!id) return;
    const preset = _presetsCache?.find(p => p.id === id);
    if (preset) _ceApplySettings(preset);
  });

  $('preset-new-btn').addEventListener('click', () => _openPresetEditor(null));
  $('pe-cancel-btn').addEventListener('click', () => $('preset-editor').classList.add('hidden'));
  $('pe-save-btn').addEventListener('click', _savePreset);
  $('pe-cq').addEventListener('input', () => { $('pe-cq-display').textContent = $('pe-cq').value; });

  loadFiltersFromStorage();

  GET('/api/settings').then(s => {
    if (s?.needs_optimize_bitrate_threshold_kbps) {
      state.bitrateThreshold = s.needs_optimize_bitrate_threshold_kbps;
    }
  }).catch(() => {});

  await fetchFolders();
  await fetchFiles();
  fetchFlaggedFiles();

  requestAnimationFrame(initResizableColumns);
  connectSSE();
  pollScanStatus();
  setInterval(pollScanStatus, 2000);
});
