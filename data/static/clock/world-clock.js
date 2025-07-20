function initClock(defaultTz) {
  const clockEl = document.getElementById('clock');
  const selectEl = document.getElementById('tz-select');
  if (defaultTz) selectEl.value = defaultTz;

  function formatISO(date, zone) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: zone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23'
    }).formatToParts(date).reduce((o,p)=>{o[p.type]=p.value;return o;},{});
    const offset = new Intl.DateTimeFormat('en-US', {timeZone: zone, timeZoneName: 'longOffset'})
      .formatToParts(date)
      .find(p => p.type === 'timeZoneName').value.replace('GMT','');
    return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}${offset}`;
  }

  function update() {
    const zone = selectEl.value;
    clockEl.textContent = formatISO(new Date(), zone);
  }

  selectEl.addEventListener('change', update);
  update();
  setInterval(update, 1000);
}
