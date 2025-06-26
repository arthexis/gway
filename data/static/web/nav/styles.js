    function styleSelectChanged(sel) {
        var css = sel.value;
        var url = window.location.pathname + window.location.search.replace(/([?&])css=[^&]*(&|$)/, '$1').replace(/^\\?|&$/g, '');
        url += (url.indexOf('?') === -1 ? '?' : '&') + 'css=' + encodeURIComponent(css);
        window.location = url;
    }