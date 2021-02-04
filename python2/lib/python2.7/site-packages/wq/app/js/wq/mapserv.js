/*
 * wq.app v1.1.2 - @wq/map/mapserv 1.1.2
 * Extension to wq/map.js with support for WMS and ESRI services
 * (c) 2016-2019, S. Andrew Sheppard
 * https://wq.io/license
 */

define(['./map', 'leaflet', 'esri-leaflet', 'leaflet.wms'], function (map, L, esri, wms) { 'use strict';

map = map && map.hasOwnProperty('default') ? map['default'] : map;
L = L && L.hasOwnProperty('default') ? L['default'] : L;
wms = wms && wms.hasOwnProperty('default') ? wms['default'] : wms;

map.addBasemapType('esri-basemap', function (conf) {
    var layer;

    if (conf.labels) {
        layer = L.layerGroup([esri.basemapLayer(conf.layer, conf), esri.basemapLayer(conf.layer + 'Labels', conf)]);
    } else {
        layer = esri.basemapLayer(conf.layer, conf);
    }

    return layer;
});
map.addBasemapType('esri-tiled', function (conf) {
    return esri.tiledMapLayer(conf);
});
map.addOverlayType('esri-dynamic', function (conf) {
    return esri.dynamicMapLayer(conf);
});
map.addOverlayType('esri-tiled', function (conf) {
    return esri.tiledMapLayer(conf);
});
map.addOverlayType('esri-feature', function (conf) {
    return esri.featureLayer(conf);
});
map.addBasemapType('wms-tiled', function (conf) {
    return wms.tileLayer(conf.url, conf);
});
map.addOverlayType('wms', function (conf) {
    return wms.overlay(conf.url, conf);
});
map.addOverlayType('wms-tiled', function (conf) {
    return wms.tileLayer(conf.url, conf);
});

return map;

});
