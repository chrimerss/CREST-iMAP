/*
 * wq.app v1.1.2 - @wq/app/spinner 1.1.2
 * Wrapper for jQuery Mobile's spinner
 * (c) 2012-2019, S. Andrew Sheppard
 * https://wq.io/license
 */

define(function () { 'use strict';

// Exported module object
var spin = {};
var jqm;

spin.start = function (msg, duration, opts) {
    if (window.jQuery) {
        jqm = window.jQuery.mobile;
    }

    if (!jqm) {
        return;
    }

    if (!opts) {
        opts = {};
    }

    if (msg) {
        opts.text = msg;
        opts.textVisible = true;
    }

    jqm.loading('show', opts);

    if (duration) {
        setTimeout(spin.stop, duration * 1000);
    }
};

spin.stop = function () {
    if (!jqm) {
        return;
    }

    jqm.loading('hide');
};

return spin;

});
