// Live blog support for entries with LiveUpdate records.
// Expects <div id="live-updates" data-entry-id="..." [data-poll="1"]>
// containing server-rendered updates, each with a data-update-id attribute.
(() => {
  const POLL_INTERVAL_MS = 5000;

  const liveUpdatesDiv = document.getElementById('live-updates');
  if (!liveUpdatesDiv) {
    return;
  }
  const entryId = liveUpdatesDiv.dataset.entryId;

  let sortOrder = 'oldest-first';
  let lastUpdateId = null;
  liveUpdatesDiv.querySelectorAll('[data-update-id]').forEach(element => {
    const updateId = parseInt(element.dataset.updateId, 10);
    if (!isNaN(updateId) && (lastUpdateId === null || updateId > lastUpdateId)) {
      lastUpdateId = updateId;
    }
  });

  const sortLink = document.createElement('a');
  sortLink.href = '#';
  sortLink.id = 'sort-toggle';
  sortLink.textContent = 'Show latest first';
  sortLink.style.display = 'block';
  sortLink.style.marginBottom = '10px';
  sortLink.addEventListener('click', event => {
    event.preventDefault();
    if (sortOrder === 'oldest-first') {
      sortOrder = 'latest-first';
      sortLink.textContent = 'Show oldest first';
    } else {
      sortOrder = 'oldest-first';
      sortLink.textContent = 'Show latest first';
    }
    const updates = Array.from(liveUpdatesDiv.children);
    updates.sort((a, b) => {
      const aId = parseInt(a.dataset.updateId, 10);
      const bId = parseInt(b.dataset.updateId, 10);
      return sortOrder === 'latest-first' ? bId - aId : aId - bId;
    });
    updates.forEach(update => liveUpdatesDiv.appendChild(update));
  });
  liveUpdatesDiv.parentNode.insertBefore(sortLink, liveUpdatesDiv);

  // Matches the markup in templates/entry_updates.html
  function renderUpdate(update) {
    const div = document.createElement('div');
    div.id = `live-update-${update.id}`;
    div.dataset.updateId = update.id;
    const p = document.createElement('p');
    const strong = document.createElement('strong');
    strong.textContent = update.created_str;
    p.appendChild(strong);
    p.insertAdjacentHTML('beforeend', ' ' + update.content);
    div.appendChild(p);
    return div;
  }

  function pollUpdates() {
    if (document.hidden) {
      setTimeout(pollUpdates, POLL_INTERVAL_MS);
      return;
    }
    let url = `/updates/${entryId}.json`;
    if (lastUpdateId !== null) {
      url += `?since=${lastUpdateId}`;
    }
    let keepPolling = true;
    fetch(url)
      .then(response => response.json())
      .then(data => {
        // Polling was switched off for this entry in the admin
        if (data.poll === false) {
          keepPolling = false;
        }
        const fragment = document.createDocumentFragment();
        const newElements = [];
        (data.updates || []).forEach(update => {
          if (document.getElementById(`live-update-${update.id}`)) {
            return;
          }
          newElements.push(renderUpdate(update));
          if (lastUpdateId === null || update.id > lastUpdateId) {
            lastUpdateId = update.id;
          }
        });
        if (sortOrder === 'latest-first') {
          newElements.reverse();
        }
        newElements.forEach(element => fragment.appendChild(element));
        if (sortOrder === 'oldest-first') {
          liveUpdatesDiv.appendChild(fragment);
        } else {
          liveUpdatesDiv.insertBefore(fragment, liveUpdatesDiv.firstChild);
        }
      })
      .catch(error => {
        console.error('Error fetching updates:', error);
      })
      .finally(() => {
        if (keepPolling) {
          setTimeout(pollUpdates, POLL_INTERVAL_MS);
        }
      });
  }

  if (liveUpdatesDiv.dataset.poll) {
    pollUpdates();
  }
})();
