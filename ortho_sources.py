"""Fixed, trusted orthophoto WMS providers (Web Mercator)."""
SOURCES = {
    'pnoa': {'label':'PNOA IGN','url':'https://www.ign.es/wms-inspire/pnoa-ma','layer':'OI.OrthoimageCoverage','size':4096},
    'itacyl': {'label':'ITACyL Castilla y León','url':'https://orto.wms.itacyl.es/WMS','layer':'Ortofoto_CyL','size':4000},
}


def provider(source='pnoa'):
    if not isinstance(source,str) or source not in SOURCES:
        raise ValueError('Selecciona PNOA o ITACyL como fuente de ortofoto.')
    return SOURCES[source]


def image_key(bbox,source='pnoa'):
    provider(source)
    return bbox if source=='pnoa' else (source,bbox)
