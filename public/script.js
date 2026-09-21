document.addEventListener('DOMContentLoaded', () => {
  const dateDisplay = document.getElementById('date-display');
  const viewConfig = document.getElementById('view-config');
  const viewAuth = document.getElementById('view-auth');
  const viewDashboard = document.getElementById('view-dashboard');
  const dashboardActions = document.getElementById('dashboard-actions');

  const btnRefresh = document.getElementById('btn-refresh');

  const calendarList = document.getElementById('calendar-list');
  const mailList = document.getElementById('mail-list');
  const directDebitBanner = document.getElementById('direct-debit-banner');
  const directDebitList = document.getElementById('direct-debit-list');
  const shippingSummary = document.getElementById('shipping-summary');

  const memo = document.getElementById('memo');
  const saveState = document.getElementById('save-state');
  let memoTimer = null;
  let memoLoaded = false;

  updateHeaderDate();
  checkStatus();
  loadMemo();

  btnRefresh && btnRefresh.addEventListener('click', () => {
    btnRefresh.innerText = '🔄 更新中...';
    loadDashboardData();
  });

  memo.addEventListener('input', () => {
    if (!memoLoaded) return;
    clearTimeout(memoTimer);
    memoTimer = setTimeout(saveMemo, 600);
  });

  function updateHeaderDate() {
    const days = ['日', '月', '火', '水', '木', '金', '土'];
    const now = new Date();
    dateDisplay.innerText = `${now.getFullYear()}年${now.getMonth() + 1}月${now.getDate()}日(${days[now.getDay()]})`;
    const todayShortDate = document.getElementById('today-short-date');
    if (todayShortDate) {
      todayShortDate.innerText = `${now.getMonth() + 1}/${now.getDate()}(${days[now.getDay()]})`;
    }
  }

  function checkStatus() {
    fetch('/api/status')
      .then(res => res.json())
      .then(status => {
        viewConfig.classList.add('hidden');
        viewAuth.classList.add('hidden');
        viewDashboard.classList.add('hidden');
        dashboardActions.classList.add('hidden');

        if (!status.has_credentials) {
          viewConfig.classList.remove('hidden');
        } else if (!status.has_token) {
          viewAuth.classList.remove('hidden');
        } else {
          viewDashboard.classList.remove('hidden');
          dashboardActions.classList.remove('hidden');
          loadDashboardData();
        }
      })
      .catch(err => {
        console.error('Status check failed:', err);
      });
  }

  function loadDashboardData() {
    fetch('/api/data')
      .then(res => {
        if (res.status === 410) {
          checkStatus();
          throw new Error('Unauthorized');
        }
        return res.json();
      })
      .then(data => {
        if (btnRefresh) btnRefresh.innerText = '🔄 更新する';
        if (data.error) {
          console.error('データの取得に失敗しました:', data.error);
          return;
        }
        renderCalendar(data.calendar);
        renderMail(data.payment_mail);
        renderDirectDebit(data.direct_debit_mail);
        renderShippingSummary(data.shipping_count);
      })
      .catch(err => {
        if (btnRefresh) btnRefresh.innerText = '🔄 更新する';
        console.error('Data load failed:', err);
      });
  }

  function loadMemo() {
    fetch('/api/memo')
      .then(res => res.json())
      .then(data => {
        memo.value = data.text || '';
        memoLoaded = true;
      })
      .catch(() => { memoLoaded = true; });
  }

  function saveMemo() {
    fetch('/api/memo', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: memo.value })
    })
      .then(res => res.json())
      .then(data => {
        if (data.status === 'ok') {
          saveState.classList.add('show');
          setTimeout(() => saveState.classList.remove('show'), 1500);
        }
      })
      .catch(err => console.error('memo save failed', err));
  }

  function renderCalendar(events) {
    calendarList.innerHTML = '';

    if (events.length === 0) {
      calendarList.innerHTML = `<div class="empty-state">今日から3日間の予定はありません。</div>`;
      return;
    }

    events.forEach(event => {
      const timeClass = event.all_day ? 'event-time all-day' : 'event-time';
      const card = document.createElement('div');
      card.className = 'item-card';
      const dateLabel = event.date_label ? `${escapeHtml(event.date_label)} ` : '';
      card.innerHTML = `
        <div class="${timeClass}">${dateLabel}${event.display_time}</div>
        <div class="event-title">${escapeHtml(event.summary)}</div>
      `;
      calendarList.appendChild(card);
    });
  }

  function renderMail(mails) {
    mailList.innerHTML = '';

    if (mails.length === 0) {
      mailList.innerHTML = `<div class="empty-state">確認が必要な未読メールはありません。</div>`;
      return;
    }

    mails.forEach(mail => {
      const card = document.createElement('div');
      card.className = 'mail-card urgent';

      const dateObj = new Date(mail.date);
      const dateStr = isNaN(dateObj.getTime()) ? mail.date : `${dateObj.getMonth() + 1}/${dateObj.getDate()} ${String(dateObj.getHours()).padStart(2, '0')}:${String(dateObj.getMinutes()).padStart(2, '0')}`;

      card.innerHTML = `
        <span class="mail-flag">${escapeHtml(mail.category || '重要')}</span>
        <div class="mail-header">
          <span class="mail-sender" title="${escapeHtml(mail.from)}">${escapeHtml(mail.from)}</span>
          <span class="mail-date">${escapeHtml(dateStr)}</span>
        </div>
        <div class="mail-subject">${escapeHtml(mail.subject)}</div>
        <div class="mail-snippet">${escapeHtml(mail.snippet)}</div>
      `;
      mailList.appendChild(card);
    });
  }

  function renderDirectDebit(mails) {
    if (!directDebitBanner || !directDebitList) return;
    mails = mails || [];

    if (mails.length === 0) {
      directDebitBanner.classList.add('hidden');
      directDebitList.innerHTML = '';
      return;
    }

    directDebitBanner.classList.remove('hidden');
    directDebitList.innerHTML = '';
    mails.forEach(mail => {
      const dateObj = new Date(mail.date);
      const dateStr = isNaN(dateObj.getTime()) ? mail.date : `${dateObj.getMonth() + 1}/${dateObj.getDate()} ${String(dateObj.getHours()).padStart(2, '0')}:${String(dateObj.getMinutes()).padStart(2, '0')}`;

      const card = document.createElement('div');
      card.className = 'item-card direct-debit-card';
      card.innerHTML = `
        <div class="mail-header">
          <span class="mail-sender" title="${escapeHtml(mail.from)}">${escapeHtml(mail.from)}</span>
          <span class="mail-date">${escapeHtml(dateStr)}</span>
        </div>
        <div class="mail-subject">${escapeHtml(mail.subject)}</div>
        <div class="mail-snippet">${escapeHtml(mail.snippet)}</div>
      `;
      directDebitList.appendChild(card);
    });
  }

  function renderShippingSummary(count) {
    if (!shippingSummary) return;
    if (!count || count <= 0) {
      shippingSummary.classList.add('hidden');
      shippingSummary.innerText = '';
      return;
    }
    shippingSummary.classList.remove('hidden');
    shippingSummary.innerText = `📦 発送・配達：${count}件`;
  }

  function escapeHtml(string) {
    if (!string) return '';
    const div = document.createElement('div');
    div.textContent = string;
    return div.innerHTML;
  }
});
