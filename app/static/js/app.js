document.querySelectorAll('form').forEach((form) => {
  form.addEventListener('submit', () => {
    form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach((button) => {
      button.setAttribute('aria-disabled', 'true');
    });
  });
});

const checklist = document.querySelector('#parts-checklist');
if (checklist) {
  const rows = [...checklist.querySelectorAll('.part-row')];
  const progressBar = document.querySelector('#parts-progress-bar');
  const progressLabel = document.querySelector('#progress-label');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const queueKey = 'brickshelf-progress-queue';
  const readQueue = () => JSON.parse(localStorage.getItem(queueKey) || '{}');
  const writeQueue = (queue) => localStorage.setItem(queueKey, JSON.stringify(queue));

  const valuesForRow = (row) => {
    const count = row.querySelector('.part-count');
    const input = row.querySelector('.part-found-quantity');
    const statusSelect = row.querySelector('.part-status-select');
    return {count, input, statusSelect, required: Number(count.dataset.required), found: Number(input.value) || 0};
  };

  const updateRow = (row) => {
    const {input, required, found} = valuesForRow(row);
    const safeValue = Math.min(Math.max(found, 0), required);
    input.value = String(safeValue);
    row.querySelector('.part-progress-check').checked = required > 0 && safeValue >= required;
    row.classList.toggle('is-partial', safeValue > 0 && safeValue < required);
    row.dataset.status = row.querySelector('.part-status-select').value;
  };

  const updateProgress = () => {
    const totals = rows.reduce((result, row) => {
      const values = valuesForRow(row);
      result.found += Math.min(values.found, values.required);
      result.required += values.required;
      return result;
    }, {found: 0, required: 0});
    const percentage = totals.required ? Math.round((totals.found / totals.required) * 100) : 0;
    progressBar.style.width = `${percentage}%`;
    progressBar.parentElement.setAttribute('aria-valuenow', String(percentage));
    progressLabel.textContent = `${totals.found} / ${totals.required}`;
  };

  const saveProgress = async (row) => {
    const {count, required, found, statusSelect} = valuesForRow(row);
    const indicator = row.querySelector('.save-indicator');
    const queueId = `${count.dataset.url}::${count.dataset.itemKey}`;
    const change = {url: count.dataset.url, item_key: count.dataset.itemKey, found_quantity: found, required_quantity: required, status: statusSelect.value};
    const queue = readQueue();
    queue[queueId] = change;
    writeQueue(queue);
    indicator.textContent = navigator.onLine ? '…' : 'offline';
    row.classList.toggle('save-pending', !navigator.onLine);
    try {
      const response = await fetch(change.url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify(change),
      });
      if (!response.ok) throw new Error('save failed');
      const currentQueue = readQueue();
      delete currentQueue[queueId];
      writeQueue(currentQueue);
      row.classList.remove('save-pending', 'save-failed');
      indicator.textContent = '✓';
      window.setTimeout(() => { if (!row.classList.contains('save-pending')) indicator.textContent = ''; }, 1200);
    } catch (_error) {
      row.classList.add('save-pending');
      indicator.textContent = 'offline';
    }
  };

  const pending = readQueue();
  rows.forEach((row) => {
    const {count, input, required} = valuesForRow(row);
    const queueId = `${count.dataset.url}::${count.dataset.itemKey}`;
    if (pending[queueId]) {
      input.value = String(Math.min(Math.max(pending[queueId].found_quantity, 0), required));
      if (pending[queueId].status) row.querySelector('.part-status-select').value = pending[queueId].status;
      row.classList.add('save-pending');
      row.querySelector('.save-indicator').textContent = 'offline';
    }
    updateRow(row);
    let saveTimer;
    input.addEventListener('input', () => {
      const statusSelect = row.querySelector('.part-status-select');
      const value = Math.min(Math.max(Number(input.value) || 0, 0), required);
      if (required > 0 && value >= required) statusSelect.value = 'found';
      else if (statusSelect.value === 'found') statusSelect.value = 'pending';
      updateRow(row);
      updateProgress();
      window.clearTimeout(saveTimer);
      saveTimer = window.setTimeout(() => saveProgress(row), 350);
    });
    row.querySelector('.part-progress-check').addEventListener('change', (event) => {
      input.value = event.target.checked ? String(required) : '0';
      row.querySelector('.part-status-select').value = event.target.checked ? 'found' : 'pending';
      updateRow(row);
      updateProgress();
      saveProgress(row);
    });
    row.querySelectorAll('.quantity-step').forEach((button) => {
      button.addEventListener('click', () => {
        input.value = String(Math.min(Math.max((Number(input.value) || 0) + Number(button.dataset.delta), 0), required));
        input.dispatchEvent(new Event('input'));
      });
    });
    row.querySelector('.part-status-select').addEventListener('change', (event) => {
      if (event.target.value === 'found') input.value = String(required);
      updateRow(row);
      updateProgress();
      saveProgress(row);
    });
  });
  updateProgress();

  document.querySelector('#part-search')?.addEventListener('input', (event) => {
    const query = event.target.value.trim().toLowerCase();
    checklist.querySelectorAll('.part-row').forEach((row) => {
      row.classList.toggle('is-hidden', Boolean(query) && !row.dataset.search.includes(query));
    });
  });

  const partsList = checklist.querySelector('.parts-list');
  const naturalCompare = new Intl.Collator('de', {numeric: true, sensitivity: 'base'}).compare;
  const groupLabels = {pending: 'Noch suchen', found: 'Gefunden', missing: 'Fehlt sicher', wrong_color: 'Falsche Farbe', alternative: 'Alternative vorhanden'};
  const applyGrouping = () => {
    partsList.querySelectorAll('.part-group-heading').forEach((heading) => heading.remove());
    const criterion = document.querySelector('#part-group')?.value || 'none';
    if (criterion === 'none') return;
    let lastGroup = null;
    [...partsList.querySelectorAll('.part-row')].forEach((row) => {
      const group = criterion === 'color' ? row.dataset.colorName : (criterion === 'type' ? row.dataset.typeGroup : groupLabels[row.dataset.status]);
      if (group !== lastGroup) {
        const heading = document.createElement('div');
        heading.className = 'part-group-heading';
        heading.textContent = group || 'Sonstige';
        partsList.insertBefore(heading, row);
        lastGroup = group;
      }
    });
  };
  document.querySelector('#part-sort')?.addEventListener('change', (event) => {
    partsList.querySelectorAll('.part-group-heading').forEach((heading) => heading.remove());
    const [criterion, direction = 'asc'] = event.target.value.split('-');
    const sortedRows = [...partsList.querySelectorAll('.part-row')];
    sortedRows.sort((left, right) => {
      if (criterion === 'original') {
        return Number(left.dataset.originalIndex) - Number(right.dataset.originalIndex);
      }
      if (criterion === 'open' || criterion === 'done') {
        const leftDone = left.querySelector('.part-progress-check').checked ? 1 : 0;
        const rightDone = right.querySelector('.part-progress-check').checked ? 1 : 0;
        return criterion === 'open' ? leftDone - rightDone : rightDone - leftDone;
      }
      let comparison;
      if (criterion === 'quantity') {
        comparison = Number(left.dataset.quantity) - Number(right.dataset.quantity);
      } else {
        const dataKey = criterion === 'part'
          ? 'partNumber'
          : (criterion === 'name' ? 'partName' : 'colorName');
        comparison = naturalCompare(left.dataset[dataKey], right.dataset[dataKey]);
      }
      if (comparison === 0) {
        comparison = Number(left.dataset.originalIndex) - Number(right.dataset.originalIndex);
      }
      return direction === 'desc' ? -comparison : comparison;
    });
    sortedRows.forEach((row) => partsList.appendChild(row));
    applyGrouping();
  });
  document.querySelector('#part-group')?.addEventListener('change', () => {
    const criterion = document.querySelector('#part-group').value;
    if (criterion !== 'none') {
      const dataKey = criterion === 'color' ? 'colorName' : (criterion === 'type' ? 'typeGroup' : 'status');
      const groupedRows = [...partsList.querySelectorAll('.part-row')].sort((left, right) => naturalCompare(left.dataset[dataKey], right.dataset[dataKey]));
      groupedRows.forEach((row) => partsList.appendChild(row));
    }
    applyGrouping();
  });

  const bulkUpdate = async (complete) => {
    const visibleRows = rows.filter((row) => !row.classList.contains('is-hidden'));
    if (!visibleRows.length) return;
    if (!complete && !window.confirm(`${visibleRows.length} sichtbare Positionen wirklich abwählen?`)) return;
    const state = document.querySelector('#bulk-save-state');
    const items = visibleRows.map((row) => {
      const {count, input, required, statusSelect} = valuesForRow(row);
      input.value = complete ? String(required) : '0';
      statusSelect.value = complete ? 'found' : 'pending';
      updateRow(row);
      return {item_key: count.dataset.itemKey, found_quantity: complete ? required : 0, required_quantity: required, status: statusSelect.value};
    });
    updateProgress();
    state.textContent = 'Wird gespeichert …';
    try {
      const response = await fetch(checklist.dataset.bulkUrl, {
        method: 'POST',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
        body: JSON.stringify({items}),
      });
      if (!response.ok) throw new Error('bulk save failed');
      const queue = readQueue();
      visibleRows.forEach((row) => {
        const {count} = valuesForRow(row);
        delete queue[`${count.dataset.url}::${count.dataset.itemKey}`];
      });
      writeQueue(queue);
      state.textContent = `${items.length} Positionen gespeichert ✓`;
    } catch (_error) {
      const queue = readQueue();
      visibleRows.forEach((row, index) => {
        const {count} = valuesForRow(row);
        queue[`${count.dataset.url}::${count.dataset.itemKey}`] = {...items[index], url: count.dataset.url};
      });
      writeQueue(queue);
      state.textContent = 'Offline vorgemerkt';
    }
  };
  document.querySelector('#check-all-visible')?.addEventListener('click', () => bulkUpdate(true));
  document.querySelector('#uncheck-all-visible')?.addEventListener('click', () => bulkUpdate(false));

  window.addEventListener('online', () => {
    const queued = readQueue();
    rows.forEach((row) => {
      const {count} = valuesForRow(row);
      if (queued[`${count.dataset.url}::${count.dataset.itemKey}`]) saveProgress(row);
    });
  });
}

const sortAssistant = document.querySelector('#sort-assistant');
if (sortAssistant) {
  let cards = [...sortAssistant.querySelectorAll('.sort-card')];
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  let currentIndex = Number(sortAssistant.dataset.startIndex) || 0;
  const orderSelect = document.querySelector('#sort-assistant-order');
  const orderStorageKey = `brickshelf-sort-order:${sortAssistant.dataset.setNumber}`;
  const naturalCompare = new Intl.Collator('de', {numeric: true, sensitivity: 'base'}).compare;
  const applyCardOrder = (order, preserveCurrent = true) => {
    const currentItemKey = cards[currentIndex]?.dataset.itemKey;
    const [criterion, direction = 'asc'] = order.split('-');
    cards.sort((left, right) => {
      if (criterion === 'original') {
        return Number(left.dataset.originalIndex) - Number(right.dataset.originalIndex);
      }
      if (criterion === 'open' || criterion === 'done') {
        const leftDone = Number(left.querySelector('.sort-found').value) >= Number(left.dataset.required) ? 1 : 0;
        const rightDone = Number(right.querySelector('.sort-found').value) >= Number(right.dataset.required) ? 1 : 0;
        if (leftDone !== rightDone) return criterion === 'open' ? leftDone - rightDone : rightDone - leftDone;
        return Number(left.dataset.originalIndex) - Number(right.dataset.originalIndex);
      }
      let comparison;
      if (criterion === 'quantity') {
        comparison = Number(left.dataset.quantity) - Number(right.dataset.quantity);
      } else {
        const dataKey = criterion === 'part'
          ? 'partNumber'
          : (criterion === 'name' ? 'partName' : 'colorName');
        comparison = naturalCompare(left.dataset[dataKey], right.dataset[dataKey]);
      }
      if (comparison === 0) {
        comparison = Number(left.dataset.originalIndex) - Number(right.dataset.originalIndex);
      }
      return direction === 'desc' ? -comparison : comparison;
    });
    if (preserveCurrent) {
      const preservedIndex = cards.findIndex((card) => card.dataset.itemKey === currentItemKey);
      currentIndex = preservedIndex >= 0 ? preservedIndex : 0;
    } else {
      currentIndex = 0;
    }
  };
  const savedOrder = localStorage.getItem(orderStorageKey);
  if (savedOrder && [...orderSelect.options].some((option) => option.value === savedOrder)) {
    orderSelect.value = savedOrder;
  }
  applyCardOrder(orderSelect.value);
  const localPosition = localStorage.getItem(`brickshelf-sort-position:${sortAssistant.dataset.setNumber}`);
  const localIndex = cards.findIndex((card) => card.dataset.itemKey === localPosition);
  if (localIndex >= 0) currentIndex = localIndex;
  const savePosition = (card) => {
    localStorage.setItem(`brickshelf-sort-position:${sortAssistant.dataset.setNumber}`, card.dataset.itemKey);
    fetch(sortAssistant.dataset.positionUrl, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken},
      body: JSON.stringify({item_key: card.dataset.itemKey}),
    }).catch(() => {});
  };
  const showCard = (index) => {
    currentIndex = (index + cards.length) % cards.length;
    cards.forEach((card, cardIndex) => card.classList.toggle('d-none', cardIndex !== currentIndex));
    document.querySelector('#sort-position').textContent = `${currentIndex + 1} / ${cards.length}`;
    savePosition(cards[currentIndex]);
  };
  const updateSortProgress = () => {
    const totals = cards.reduce((sum, card) => {
      sum.required += Number(card.dataset.required);
      sum.found += Math.min(Number(card.querySelector('.sort-found').value) || 0, Number(card.dataset.required));
      return sum;
    }, {found: 0, required: 0});
    const percent = totals.required ? Math.round(totals.found / totals.required * 100) : 0;
    document.querySelector('#sort-progress-bar').style.width = `${percent}%`;
    document.querySelector('#sort-progress-label').textContent = `${totals.found} / ${totals.required} · ${percent} %`;
  };
  const setActiveStatus = (card, status) => {
    card.dataset.status = status;
    card.querySelectorAll('[data-status]').forEach((button) => button.classList.toggle('active', button.dataset.status === status));
  };
  const saveCard = async (card) => {
    const indicator = card.querySelector('.sort-save-state');
    const change = {
      item_key: card.dataset.itemKey,
      required_quantity: Number(card.dataset.required),
      found_quantity: Number(card.querySelector('.sort-found').value) || 0,
      status: card.dataset.status,
      part_note: card.querySelector('.sort-note').value,
    };
    indicator.textContent = navigator.onLine ? 'Wird gespeichert …' : 'Offline vorgemerkt';
    try {
      const response = await fetch(card.dataset.url, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken}, body: JSON.stringify(change)});
      if (!response.ok) throw new Error('save failed');
      const queue = JSON.parse(localStorage.getItem('brickshelf-progress-queue') || '{}');
      delete queue[`${card.dataset.url}::${card.dataset.itemKey}`];
      localStorage.setItem('brickshelf-progress-queue', JSON.stringify(queue));
      indicator.textContent = 'Gespeichert ✓';
      navigator.vibrate?.(35);
    } catch (_error) {
      const queue = JSON.parse(localStorage.getItem('brickshelf-progress-queue') || '{}');
      queue[`${card.dataset.url}::${card.dataset.itemKey}`] = {...change, url: card.dataset.url};
      localStorage.setItem('brickshelf-progress-queue', JSON.stringify(queue));
      indicator.textContent = 'Offline vorgemerkt';
    }
  };
  const pendingSortChanges = JSON.parse(localStorage.getItem('brickshelf-progress-queue') || '{}');
  cards.forEach((card) => {
    const input = card.querySelector('.sort-found');
    const required = Number(card.dataset.required);
    const pendingChange = pendingSortChanges[`${card.dataset.url}::${card.dataset.itemKey}`];
    if (pendingChange) {
      input.value = String(pendingChange.found_quantity);
      card.dataset.status = pendingChange.status || card.dataset.status;
      if (pendingChange.part_note !== undefined) card.querySelector('.sort-note').value = pendingChange.part_note;
      card.querySelector('.sort-save-state').textContent = 'Offline vorgemerkt';
    }
    setActiveStatus(card, card.dataset.status);
    let timer;
    const changed = () => {
      input.value = String(Math.min(Math.max(Number(input.value) || 0, 0), required));
      if (Number(input.value) >= required && required > 0) setActiveStatus(card, 'found');
      else if (card.dataset.status === 'found') setActiveStatus(card, 'pending');
      updateSortProgress();
      window.clearTimeout(timer);
      timer = window.setTimeout(() => saveCard(card), 350);
    };
    input.addEventListener('input', changed);
    card.querySelectorAll('.sort-step').forEach((button) => button.addEventListener('click', () => { input.value = String((Number(input.value) || 0) + Number(button.dataset.delta)); changed(); }));
    card.querySelector('.sort-complete').addEventListener('click', () => { input.value = String(required); setActiveStatus(card, 'found'); updateSortProgress(); saveCard(card); window.setTimeout(() => showCard(currentIndex + 1), 250); });
    card.querySelectorAll('[data-status]').forEach((button) => button.addEventListener('click', () => { setActiveStatus(card, button.dataset.status); saveCard(card); }));
    card.querySelector('.sort-note').addEventListener('input', () => { window.clearTimeout(timer); timer = window.setTimeout(() => saveCard(card), 500); });
  });
  document.querySelector('#sort-prev').addEventListener('click', () => showCard(currentIndex - 1));
  document.querySelector('#sort-next').addEventListener('click', () => showCard(currentIndex + 1));
  document.querySelector('#sort-next-open').addEventListener('click', () => {
    for (let offset = 1; offset <= cards.length; offset += 1) {
      const candidate = (currentIndex + offset) % cards.length;
      if (Number(cards[candidate].querySelector('.sort-found').value) < Number(cards[candidate].dataset.required)) { showCard(candidate); break; }
    }
  });
  orderSelect.addEventListener('change', () => {
    applyCardOrder(orderSelect.value, false);
    localStorage.setItem(orderStorageKey, orderSelect.value);
    showCard(currentIndex);
  });
  window.addEventListener('online', () => {
    const queued = JSON.parse(localStorage.getItem('brickshelf-progress-queue') || '{}');
    cards.forEach((card) => {
      if (queued[`${card.dataset.url}::${card.dataset.itemKey}`]) saveCard(card);
    });
  });
  document.addEventListener('keydown', (event) => {
    if (event.target.matches('input, textarea')) return;
    if (event.key === 'ArrowLeft') showCard(currentIndex - 1);
    if (event.key === 'ArrowRight') showCard(currentIndex + 1);
  });
  showCard(currentIndex);
  updateSortProgress();
}

const setAccessibilityMode = (enabled) => {
  document.body.classList.toggle('accessibility-mode', enabled);
  localStorage.setItem('brickshelf-accessibility', enabled ? '1' : '0');
  document.querySelectorAll('#display-mode-toggle, #accessibility-toggle').forEach((button) => { button.textContent = enabled ? 'Normalansicht' : 'Großansicht'; });
};
setAccessibilityMode(localStorage.getItem('brickshelf-accessibility') === '1');
document.querySelectorAll('#display-mode-toggle, #accessibility-toggle').forEach((button) => button.addEventListener('click', () => setAccessibilityMode(!document.body.classList.contains('accessibility-mode'))));

const themeToggle = document.querySelector('#theme-toggle');
const themePreference = window.matchMedia('(prefers-color-scheme: dark)');
const applyTheme = (theme, persist = false) => {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  document.documentElement.dataset.bsTheme = dark ? 'dark' : 'light';
  document.querySelector('#theme-color')?.setAttribute('content', dark ? '#091317' : '#172b35');
  if (themeToggle) {
    themeToggle.setAttribute('aria-pressed', dark ? 'true' : 'false');
    themeToggle.querySelector('.theme-toggle-icon').textContent = dark ? '☀' : '◐';
    themeToggle.querySelector('.theme-toggle-label').textContent = dark ? 'Hellmodus' : 'Darkmode';
  }
  if (persist) localStorage.setItem('brickhoard-theme', dark ? 'dark' : 'light');
};
applyTheme(document.documentElement.dataset.theme || 'light');
themeToggle?.addEventListener('click', () => {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark', true);
});
themePreference.addEventListener?.('change', (event) => {
  if (!localStorage.getItem('brickhoard-theme')) applyTheme(event.matches ? 'dark' : 'light');
});

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/service-worker.js'));
}

let installPrompt;
const installButton = document.querySelector('#install-app');
window.addEventListener('beforeinstallprompt', (event) => {
  event.preventDefault();
  installPrompt = event;
  installButton?.classList.remove('d-none');
});
installButton?.addEventListener('click', async () => {
  if (!installPrompt) return;
  await installPrompt.prompt();
  installPrompt = null;
  installButton.classList.add('d-none');
});

document.querySelector('#logout-form')?.addEventListener('submit', () => {
  localStorage.removeItem('brickshelf-progress-queue');
  navigator.serviceWorker?.controller?.postMessage('CLEAR_PRIVATE_CACHE');
});
