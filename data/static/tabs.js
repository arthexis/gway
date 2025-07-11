// file: data/static/tabs.js
(function(){
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.gw-tabs').forEach(function(box){
      var tabs = box.querySelectorAll('.gw-tab');
      var blocks = box.querySelectorAll('.gw-tab-block');
      function activate(i){
        tabs.forEach(function(t,idx){ t.classList.toggle('active', idx===i); });
        blocks.forEach(function(b,idx){ b.classList.toggle('active', idx===i); });
      }
      tabs.forEach(function(tab,i){
        tab.addEventListener('click', function(){ activate(i); });
      });
      if(tabs.length){ activate(0); }
    });
  });
})();
