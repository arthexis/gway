// file: data/static/tabs.js
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.gw-tabs').forEach(function(box){
      var tabs = box.querySelectorAll('.gw-tab');
      var blocks = box.querySelectorAll('.gw-tab-block');
      var url = new URL(window.location);
      function activate(i){
        tabs.forEach(function(t,idx){ t.classList.toggle('active', idx===i); });
        blocks.forEach(function(b,idx){ b.classList.toggle('active', idx===i); });
        box.__activeTab = i;
        if(url.searchParams.get('tab') !== String(i)){
          url.searchParams.set('tab', i);
          history.replaceState(null, '', url);
        }
      }
      tabs.forEach(function(tab,i){
        tab.addEventListener('click', function(){ activate(i); });
      });
      blocks.forEach(function(block,idx){
        block.querySelectorAll('form').forEach(function(form){
          form.addEventListener('submit', function(){
            var tabIdx = box.__activeTab ?? idx;
            var urlf = new URL(form.getAttribute('action') || window.location, window.location);
            urlf.searchParams.set('tab', tabIdx);
            form.setAttribute('action', urlf.pathname + urlf.search);
          });
        });
      });
      var start = parseInt(url.searchParams.get('tab'));
      if(isNaN(start) || start < 0 || start >= tabs.length) start = 0;
      if(tabs.length){ activate(start); }
    });
  });
})();
