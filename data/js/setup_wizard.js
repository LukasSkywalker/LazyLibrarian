/*  This file is part of Lazylibrarian.
 *  The setup wizard: typical settings for the user's country, see lazylibrarian/setupwizard.py.
 *  A native <dialog> without jQuery or Bootstrap, so the bookstrap (Bootstrap 3) and the modern
 *  (Bootstrap 5) interfaces share it. Strings come translated from setup_wizard.html as window.LLW_T.
 */
(function () {
  'use strict';
  var T = window.LLW_T || {};
  var dlg = null, data = null, state = {}, step = 0, autoOpened = false, busy = false;

  function t(key) { return T[key] || key; }

  function el(tag, attrs, kids) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') { node.textContent = attrs[k]; }
      else if (k === 'class') { node.className = attrs[k]; }
      else if (k.slice(0, 2) === 'on') { node.addEventListener(k.slice(2), attrs[k]); }
      else if (attrs[k] !== false && attrs[k] !== null && attrs[k] !== undefined) { node.setAttribute(k, attrs[k]); }
    });
    (kids || []).forEach(function (kid) { if (kid) { node.appendChild(typeof kid === 'string' ? document.createTextNode(kid) : kid); } });
    return node;
  }

  function show(value) {
    if (value === true) { return t('on'); }
    if (value === false) { return t('off'); }
    return value === '' || value === null || value === undefined ? '—' : String(value);
  }

  function getJSON(url) {
    return fetch(url, {credentials: 'same-origin'}).then(function (r) {
      if (!r.ok) { throw new Error(r.status + ' ' + r.statusText); }
      return r.json();
    });
  }

  function post(url, body) {
    return fetch(url, {method: 'POST', credentials: 'same-origin', body: new URLSearchParams(body)}).then(function (r) {
      if (!r.ok) { throw new Error(r.status + ' ' + r.statusText); }
      return r.json();
    });
  }

  function toast(text) {
    var node = el('div', {'class': 'llw-toast', role: 'status', text: text});
    document.body.appendChild(node);
    setTimeout(function () { node.remove(); }, 3500);
  }

  function rows() {
    var all = [];
    (data ? data.steps : []).forEach(function (s) { all = all.concat(s.rows); });
    return all;
  }

  // the proposals of a newly loaded country replace the old ones, except where the user edited a row
  function load(country) {
    var langs = (navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || '']).join(',');
    var url = 'wizard_presets?langs=' + encodeURIComponent(langs) + (country ? '&country=' + encodeURIComponent(country) : '');
    busy = true; render();
    return getJSON(url).then(function (res) {
      data = res;
      rows().forEach(function (row) {
        var old = state[row.key];
        if (!old || !old.edited) { state[row.key] = {ticked: row.changed, value: row.proposed, edited: false}; }
      });
      busy = false; render();
    }).catch(function (e) { busy = false; render(String(e)); });
  }

  function setValue(row, value) {
    var s = state[row.key];
    s.value = value; s.edited = true; s.ticked = value !== row.current;
  }

  function folderBadge(row, badge) {
    var value = state[row.key].value;
    clearTimeout(badge._timer);
    badge._timer = setTimeout(function () {
      getJSON('wizard_check_folder?path=' + encodeURIComponent(value)).then(function (res) {
        badge.textContent = t('folder_' + res.status);
        badge.className = 'llw-badge llw-' + res.status;
      }).catch(function () {});
    }, 400);
  }

  function editor(row) {
    var s = state[row.key];
    var tick = function () { box.checked = s.ticked; };
    var box = null, input;
    if (row.kind === 'bool') {
      input = el('input', {type: 'checkbox', role: 'switch', onchange: function () { setValue(row, input.checked); tick(); }});
      input.checked = !!s.value;
      input = el('label', {'class': 'llw-switch'}, [input, ' ' + t('on')]);
    } else if (row.kind === 'choice') {
      input = el('select', {onchange: function () { setValue(row, input.value); tick(); }},
        row.choices.map(function (c) { return el('option', {value: c, text: c, selected: c === s.value ? 'selected' : false}); }));
    } else if (row.kind === 'months') {
      input = el('span', {'class': 'llw-muted', text: row.proposed});
    } else {
      input = el('input', {type: 'text', value: s.value, spellcheck: 'false', oninput: function () {
        setValue(row, input.value); tick(); if (badge) { folderBadge(row, badge); }
      }});
    }
    var badge = row.kind === 'folder' ? el('span', {'class': 'llw-badge'}) : null;
    if (badge) { folderBadge(row, badge); }
    box = el('input', {type: 'checkbox', 'aria-label': row.label, onchange: function () { s.ticked = box.checked; }});
    box.checked = s.ticked;
    return el('div', {'class': 'llw-row' + (row.changed ? ' llw-changed' : '')}, [
      el('label', {'class': 'llw-tick'}, [box]),
      el('div', {'class': 'llw-main'}, [
        el('div', {'class': 'llw-label', text: row.label}),
        row.help ? el('div', {'class': 'llw-help', text: row.help}) : null,
        el('div', {'class': 'llw-edit'}, [input, badge]),
        el('div', {'class': 'llw-cur', text: t('current') + ': ' + show(row.current)})
      ])
    ]);
  }

  function summary() {
    var ticked = rows().filter(function (row) { return state[row.key].ticked; });
    if (!ticked.length) { return [el('p', {'class': 'llw-muted', text: t('nothing')})]; }
    return [el('table', {'class': 'llw-summary'}, [
      el('thead', {}, [el('tr', {}, [el('th'), el('th', {text: t('setting')}), el('th', {text: t('change')})])]),
      el('tbody', {}, ticked.map(function (row) {
        var box = el('input', {type: 'checkbox', checked: 'checked', 'aria-label': row.label,
          onchange: function () { state[row.key].ticked = box.checked; }});
        return el('tr', {}, [el('td', {}, [box]), el('td', {text: row.label}),
          el('td', {}, [el('span', {'class': 'llw-old', text: show(row.current)}), ' → ',
            el('strong', {text: show(state[row.key].value)})])]);
      }))
    ])];
  }

  function apply() {
    var values = {};
    rows().forEach(function (row) { if (state[row.key].ticked) { values[row.key] = state[row.key].value; } });
    if (!Object.keys(values).length) { close(); return; }
    busy = true; render();
    post('wizard_apply', {values: JSON.stringify(values)}).then(function (res) {
      busy = false;
      if (!res.ok) { render(res.error || t('failed')); return; }
      var msg = t('saved').replace('%(count)s', res.changed.length);
      if (res.warnings && res.warnings.length) { msg += ' ' + res.warnings.join(' '); }
      if (res.reload) { toast(msg); setTimeout(function () { location.reload(); }, 1200); return; }
      close(); toast(msg);
    }).catch(function (e) { busy = false; render(String(e)); });
  }

  function render(error) {
    if (!dlg) { return; }
    var steps = data ? data.steps : [];
    var last = steps.length;  // the summary
    var body = [];
    if (busy || !data) {
      body.push(el('p', {'class': 'llw-muted', text: t('loading')}));
    } else if (step < last) {
      var s = steps[step];
      if (step === 0) {
        var sel = el('select', {id: 'llw-country', onchange: function () { load(sel.value); }},
          data.countries.map(function (c) { return el('option', {value: c.code, text: c.label, selected: c.code === data.country ? 'selected' : false}); }));
        body.push(el('div', {'class': 'llw-country'}, [el('label', {'for': 'llw-country', text: t('country')}), sel]));
        body.push(el('p', {'class': 'llw-muted', text: t('intro')}));
      }
      if (s.id === 'other' && data.auth_missing) {
        body.push(el('div', {'class': 'llw-note'}, [t('auth') + ' ', el('a', {href: 'config#interface', text: t('auth_link')})]));
      }
      s.rows.forEach(function (row) { body.push(editor(row)); });
    } else {
      body = summary();
    }
    if (error) { body.unshift(el('div', {'class': 'llw-error', role: 'alert', text: error})); }

    var title = !data ? t('title') : (step < last ? steps[step].title : t('summary'));
    var dots = el('ol', {'class': 'llw-steps'}, steps.concat([{title: t('summary')}]).map(function (s, i) {
      return el('li', {'class': i === step ? 'llw-on' : (i < step ? 'llw-done' : ''), title: s.title, text: String(i + 1)});
    }));
    var foot = [
      autoOpened ? el('button', {type: 'button', 'class': 'llw-link', text: t('dismiss'), onclick: function () {
        post('wizard_dismiss', {}).catch(function () {}); close();
      }}) : null,
      el('span', {'class': 'llw-grow'}),
      el('button', {type: 'button', 'class': 'llw-btn', text: t('cancel'), onclick: close}),
      step > 0 ? el('button', {type: 'button', 'class': 'llw-btn', text: t('back'), disabled: busy ? 'disabled' : false,
        onclick: function () { step -= 1; render(); }}) : null,
      step < last ? el('button', {type: 'button', 'class': 'llw-btn', text: t('skip'), disabled: busy || !data ? 'disabled' : false,
        onclick: function () { steps[step].rows.forEach(function (row) { state[row.key].ticked = false; }); step += 1; render(); }}) : null,
      step < last
        ? el('button', {type: 'button', 'class': 'llw-btn llw-primary', text: t('next'), disabled: busy || !data ? 'disabled' : false,
          onclick: function () { step += 1; render(); }})
        : el('button', {type: 'button', 'class': 'llw-btn llw-primary', text: t('apply'), disabled: busy ? 'disabled' : false, onclick: apply})
    ];
    dlg.replaceChildren(
      el('header', {}, [el('h2', {text: title}), dots]),
      el('div', {'class': 'llw-body'}, body),
      el('footer', {}, foot)
    );
  }

  function close() { if (dlg && dlg.open) { dlg.close(); } }

  function open(auto) {
    autoOpened = !!auto;
    if (!dlg) {
      dlg = el('dialog', {'class': 'llw', 'aria-label': t('title')});
      document.body.appendChild(dlg);
    }
    step = 0; state = {}; data = null;
    render();
    if (dlg.showModal) { dlg.showModal(); } else { dlg.setAttribute('open', 'open'); }
    load('');
  }

  window.LLSetupWizard = {open: function () { open(false); }};

  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('#setupwizard')) { e.preventDefault(); open(false); }
  });

  // a new install: offer the wizard once per browser session, "don't show again" stops it for good
  function autoOpen() {
    var root = document.getElementById('llw-root');
    if (!root || root.getAttribute('data-autoopen') !== '1') { return; }
    try { if (sessionStorage.getItem('llw-offered')) { return; } sessionStorage.setItem('llw-offered', '1'); } catch (e) { /* private mode */ }
    open(true);
  }
  if (document.readyState === 'loading') { document.addEventListener('DOMContentLoaded', autoOpen); } else { autoOpen(); }
})();
