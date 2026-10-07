"""Physical RAM estimate for the server doing image processing."""
import ctypes
import os
BYTES_PER_PIXEL = 96
MODEL_RESERVE = 512*1024**2

def memory_info():
    total=available=None
    try:
        if os.name=='nt':
            class Status(ctypes.Structure):
                _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(name,ctypes.c_ulonglong) for name in ('total','available','total_page','available_page','total_virtual','available_virtual','extended')]
            status=Status();status.length=ctypes.sizeof(status)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)): raise OSError('RAM unavailable')
            total,available=int(status.total),int(status.available)
        else:
            total=os.sysconf('SC_PHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
            available=os.sysconf('SC_AVPHYS_PAGES')*os.sysconf('SC_PAGE_SIZE')
    except (OSError,AttributeError,ValueError): pass
    budget=max(0,int(available*.5)-MODEL_RESERVE) if available is not None else None
    recommended=max(1,int(budget/BYTES_PER_PIXEL/1e6)) if budget is not None else 32
    return {'total_bytes':total,'available_bytes':available,'recommended_megapixels':recommended,'bytes_per_pixel':BYTES_PER_PIXEL,'model_reserve_bytes':MODEL_RESERVE,'budget_fraction':.5,'estimated':True}
