document.addEventListener('DOMContentLoaded', () => {
  const dateDisplay = document.getElementById('date-display');
  const viewConfig = document.getElementById('view-config');
  const viewAuth = document.getElementById('view-auth');
  const viewDashboard = document.getElementById('view-dashboard');
  const dashboardActions = document.getElementById('dashboard-actions');

  const btnRefresh = document.getElementById('btn-refresh');

  const calendarList = document.getElementById('calendar-list');
  const deadlineList = document.getElementById('deadline-list');
  const yesterdayList = document.getElementById('yesterday-list');
  const yesterdayDate = document.getElementById('yesterday-date');
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
        renderDeadlines(data.deadlines);
        renderYesterday(data.yesterday_date_label, data.yesterday_events);
        renderMail(data.payment_mail);
        renderDirectDebit(data.direct_debit_mail);
        renderShippingSummary(data.shipped_count, data.delivered_count);
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

  // 同じ日付（date_label）が連続している予定を、1枚のカードにまとめる。
  // データはAPI側ですでに日時順に並んでいるため、同じ日付は必ず連続している。
  function groupByDateLabel(items) {
    const groups = [];
    let current = null;
    items.forEach(item => {
      if (!current || current.date_label !== item.date_label) {
        current = { date_label: item.date_label, items: [] };
        groups.push(current);
      }
      current.items.push(item);
    });
    return groups;
  }

  function renderCalendar(events) {
    calendarList.innerHTML = '';

    if (events.length === 0) {
      calendarList.innerHTML = `<div class="empty-state">今日から7日間の予定はありません。</div>`;
      return;
    }

    groupByDateLabel(events).forEach(group => {
      const card = document.createElement('div');
      card.className = 'item-card';
      const rows = group.items.map(event => {
        const timeClass = event.all_day ? 'event-time-inline all-day' : 'event-time-inline';
        return `<div class="event-row"><span class="${timeClass}">${escapeHtml(event.display_time)}</span><span class="event-title-inline">${escapeHtml(event.summary)}</span></div>`;
      }).join('');
      card.innerHTML = `<div class="event-date-heading">${escapeHtml(group.date_label)}</div>${rows}`;
      calendarList.appendChild(card);
    });
  }

  function renderDeadlines(deadlines) {
    deadlineList.innerHTML = '';
    deadlines = deadlines || [];

    if (deadlines.length === 0) {
      deadlineList.innerHTML = `<div class="empty-state">60日以内の期限はありません。</div>`;
      return;
    }

    groupByDateLabel(deadlines).forEach(group => {
      const soon = group.items[0].soon;
      const card = document.createElement('div');
      card.className = 'item-card deadline-card' + (soon ? ' soon' : '');
      const rows = group.items.map(item => `<div class="event-row"><span class="event-title-inline">${escapeHtml(item.summary)}</span></div>`).join('');
      card.innerHTML = `<div class="event-date-heading">${escapeHtml(group.date_label)} <span class="deadline-days">${escapeHtml(group.items[0].days_label)}</span></div>${rows}`;
      deadlineList.appendChild(card);
    });
  }

  function renderYesterday(dateLabel, events) {
    if (yesterdayDate) yesterdayDate.innerText = dateLabel || '';
    yesterdayList.innerHTML = '';
    events = events || [];

    if (events.length === 0) {
      yesterdayList.innerHTML = `<div class="empty-state">昨日の予定はありません。</div>`;
      return;
    }

    events.forEach(event => {
      const timeClass = event.all_day ? 'event-time all-day' : 'event-time';
      const card = document.createElement('div');
      card.className = 'item-card';
      card.innerHTML = `
        <div class="${timeClass}">${escapeHtml(event.display_time)}</div>
        <div class="event-title">${escapeHtml(event.summary)}</div>
      `;
      yesterdayList.appendChild(card);
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
      // タップ（クリック）したら、そのメールをGmailで直接開く。
      if (mail.id) {
        card.classList.add('tappable');
        card.addEventListener('click', () => openGmailMessage(mail.id));
      }
      mailList.appendChild(card);
    });
  }

  // GmailのメールIDから、そのメールをGmail（ブラウザ）で開く。
  // 今開いているGoogleアカウント（u/0＝一番上のアカウント）で開く点に注意。
  function openGmailMessage(mailId) {
    window.open(`https://mail.google.com/mail/u/0/#all/${mailId}`, '_blank', 'noopener');
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
      if (mail.id) {
        card.classList.add('tappable');
        card.addEventListener('click', () => openGmailMessage(mail.id));
      }
      directDebitList.appendChild(card);
    });
  }

  function renderShippingSummary(shippedCount, deliveredCount) {
    if (!shippingSummary) return;
    shippedCount = shippedCount || 0;
    deliveredCount = deliveredCount || 0;
    if (shippedCount <= 0 && deliveredCount <= 0) {
      shippingSummary.classList.add('hidden');
      shippingSummary.innerText = '';
      return;
    }
    shippingSummary.classList.remove('hidden');
    shippingSummary.innerText = `📦発送済み：${shippedCount}件　✅お届け完了：${deliveredCount}件`;
  }

  function escapeHtml(string) {
    if (!string) return '';
    const div = document.createElement('div');
    div.textContent = string;
    return div.innerHTML;
  }
});
