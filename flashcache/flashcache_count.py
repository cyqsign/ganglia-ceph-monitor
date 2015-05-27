#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import os
import re
import json
import subprocess
import traceback
import logging
descriptors = list()
osd_path = "/var/lib/ceph/osd"
fc_result = {}
dev_map_disk ={}
osd_map_dev = {}
NAME_PREFIX = 'osd_'
num = 0
logging.basicConfig(filename = "/var/log/flashcache_count.log", level = logging.CRITICAL , filemode = "a", format = "%(asctime)s - %(thread)d - %(levelname)s - %(filename)s[line:%(lineno)d]: %(message)s")
log = logging.getLogger("root")
def run_shell(cmd, timeout = 4):
    p = subprocess.Popen(
        args = cmd,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
        shell = True
    )
    #must run shell with timeout
    # define deadline
    deadline = time.time() + timeout
    poll_seconds = 0.25
    while time.time() < deadline and p.poll() == None:
        time.sleep(poll_seconds)
    # get result
    ret = p.poll()
    if ret:
        # ret != 0
        return None
    if ret == None:
        # timeout
        try:
            p.terminate()
        except:
            pass
        return None
    res = ''
    while True:
        buff = p.stdout.readline()
        res = res + buff
        if buff == '':
            break;
    return res.rstrip()

def get_osd_map_to_dev():
    global osd_map_dev
    global osd_path
    try:
        f = open('/proc/mounts')
        
    except IOError:
        f = []
    for line in f:
        if line.startswith('/'):
            mount_info = line.split()
            m = re.search(osd_path,mount_info[1])
            if m:
                path_key = mount_info[1]
                map_disk = mount_info[0]
                id = path_key.split('-')[1]
                disk = map_disk.split('/')[-1]
                osd_map_dev[id]=disk
    #print osd_map_dev 


def get_dev_map_to_disk():
    global dev_map_disk
    result = run_shell("dmsetup table")
    if result == None:
        return -1
    tiereds = re.findall(r'(tiered[0-9]+)\w*',result)
    disks = re.findall(r'(/dev/sd\w[0-9]*)\w*',result)
    if len(disks)%len(tiereds) != 0:
        return -1
    first = 0
    length = len(disks) - 1
    for key in tiereds:
        dev_map_disk[key]={}
        if first > length:
            return -1
        next = first + 1
        # "/dev/" is 5
        dev_map_disk[key]=disks[first][5:]+"+"+disks[next][5:]
        first = first + 2
    return 0

def get_key_value(key,result_list):
    for w in result_list:
        m = re.search("^"+key+"=",w)
        if m:
            ret = re.findall(r'\w+=(\d+)',w)
            return ret[0]
    return None
def update_value(id):
    global fc_result,osd_map_dev,dev_map_disk
    if id not in fc_result:
       return 
    if id not in osd_map_dev:
       return 
    if osd_map_dev[id] not in dev_map_disk:
       return 
    dev = osd_map_dev[id] 
    filename = "/proc/flashcache/"+dev_map_disk[dev]+"/flashcache_stats"
    try:
        f = open(filename)
    except IOError:
        f = []
        return  
    fc_result[id] = [] 
    for line in f:
        fc_result[id].extend(line.split(' '))
    f.close()
    return fc_result[id]

def set_current_val(filename,vals):
    
    if type(vals) != list:
        return -1
    output = open(filename,'w')
    for val in vals:
        output.write(str(val))
        output.write('\n')
    output.close()
    return 0


def get_last_val(filename):
    context = []
    if os.path.exists(filename):
        output = open(filename,'r')
        while True:
            line = output.readline()
            if not line:
                break
            context.append(line)
        output.close()
    return context
    
def get_write_miss(name):
    try:
        id = name.split('_')[-1]
        result_list = update_value(id)
        current_write_hists = get_key_value("write_hits",result_list)
        current_writes = get_key_value("writes",result_list)
        current_uncached_sequential_writes = get_key_value("uncached_sequential_writes",result_list)
        last_context = []
        last_context = get_last_val('/dev/shm/write_hists'+id)
        current_context = []
        current_context.append(current_write_hists)
        current_context.append(current_writes)
        current_context.append(current_uncached_sequential_writes)
        ret = set_current_val('/dev/shm/write_hists'+id,current_context)
        if ret != 0:
            return 0
        if len(last_context) != 3:
            return 0
        last_write_hists = last_context[0].strip('\n')
        last_writes = last_context[1].strip('\n')
        last_uncached_sequential_writes = last_context[2].strip('\n')
        current_diff = int(current_writes) - int(current_uncached_sequential_writes)
        last_diff = int(last_writes) - int(last_uncached_sequential_writes)
        if current_diff == last_diff:
            return 0
        else:
            hist_diff = int(current_write_hists) - int(last_write_hists)
            r_diff = int(current_diff) - int(last_diff)
            r = 100.0 - hist_diff*(100.0)/r_diff
            return r
    except:
        log.error("exception when do : %s" %(traceback.format_exc()))
        return 0
def get_read_miss(name):
    try:
        id = name.split('_')[-1]
        global fc_result
        if id not in fc_result:
            return 0
        result_list = update_value(id)
        current_read_hists = get_key_value("read_hits",result_list)
        current_reads = get_key_value("reads",result_list)
        current_uncached_sequential_reads = get_key_value("uncached_sequential_reads",result_list)
        last_context = []
        last_context = get_last_val('/dev/shm/read_hists'+id)
        current_context = []
        current_context.append(current_read_hists)
        current_context.append(current_reads)
        current_context.append(current_uncached_sequential_reads)
        ret = set_current_val('/dev/shm/read_hists'+id,current_context)
        if ret != 0:
            return 0
        if len(last_context) != 3:
            return 0
        last_read_hists = last_context[0].strip('\n')
        last_reads = last_context[1].strip('\n')
        last_uncached_sequential_reads = last_context[2].strip('\n')
        current_diff = int(current_reads) - int(current_uncached_sequential_reads)
        last_diff = int(last_reads) - int(last_uncached_sequential_reads)
        if current_diff == last_diff:
            return 0
        else:
            hist_diff = int(current_read_hists) - int(last_read_hists)
            r_diff = int(current_diff) - int(last_diff)
            r = 100.0 - hist_diff*(100.0)/r_diff
            return r
    except:
        log.error("exception when do : %s" %(traceback.format_exc())) 
        return 0
def get_clean_count(name):
    try:
        id = name.split('_')[-1]
        global fc_result
        if id not in fc_result:
            return 0
        result_list = update_value(id)
        current_cleanings = get_key_value("cleanings",result_list)
        last_context = []
        last_context = get_last_val('/dev/shm/cleanings'+id)
        current_context = []
        current_context.append(current_cleanings)
        ret = set_current_val('/dev/shm/cleanings'+id,current_context)
        if ret != 0:
            return 0
        if len(last_context) != 1:
            return 0
        last_cleanings = last_context[0].strip('\n')
        r = int(current_cleanings) - int(last_cleanings)
        return r
    except:
        log.error("exception when do : %s" %(traceback.format_exc())) 
        return 0

def get_metaddata_dirties(name):
    try:
        id = name.split('_')[-1]
        global fc_result
        if id not in fc_result:
            return 0
        result_list = update_value(id)
        current_dirties = get_key_value("metadata_dirties",result_list)
        last_context = []
        last_context = get_last_val('/dev/shm/metadata_dirties'+id)
        current_context = []
        current_context.append(current_dirties)
        ret = set_current_val('/dev/shm/metadata_dirties'+id,current_context)
        if ret != 0:
            return 0
        if len(last_context) != 1:
            return 0
        last_dirties = last_context[0].strip('\n')
        r = int(current_dirties) - int(last_dirties)
        return r
    except:
        log.error("exception when do : %s" %(traceback.format_exc())) 
        return 0

def get_front_merge(name):
    try:
        id = name.split('_')[-1]
        global fc_result
        if id not in fc_result:
            return 0
        result_list = update_value(id)
        current_merge = get_key_value("front_merge",result_list)
        last_context = []
        last_context = get_last_val('/dev/shm/front_merge'+id)
        current_context = []
        current_context.append(current_merge)
        ret = set_current_val('/dev/shm/front_merge'+id,current_context)
        if ret != 0:
            return 0
        if len(last_context) != 1:
            return 0
        last_merge = last_context[0].strip('\n')
        r = int(current_merge) - int(last_merge)
        return r
    except:
        log.error("exception when do : %s" %(traceback.format_exc())) 
        return 0
def metric_init(lparams):
    global dev_map_disk,osd_map_dev,fc_result
    descriptors = []
    if get_dev_map_to_disk() != 0:
        return descriptors
    get_osd_map_to_dev()
    callback_funcs = {
        0:get_write_miss,
        1:get_read_miss,
        2:get_clean_count,
        3:get_metaddata_dirties,
        4:get_front_merge
    }
    keys = {
        0:"fc_miss_write_",
        1:"fc_miss_read_",
        2:"fc_clean_count_",
        3:"fc_metaddata_dirties_",
        4:"fc_front_merge_"
    }
    descripts = {
        0:"write miss per sample interval",
        1:"read miss per sample interval",
        2:"How many dirty blocks in cache were cleaned to disk",
        3:"Every write requires a ssd update for flashcache metadata.metadata update when a block is written to cache.",
        4:"measure of how efficiently flashcache was able to merge writes to the disk"
    }
    value_types = {
        0:'float',
        1:'float',
        2:'uint',
        3:'uint',
        4:'uint'
    }

    formats = {
        0:'%f',
        1:'%f',
        2:'%u',
        3:'%u',
        4:'%u'
    }
    for key,value in osd_map_dev.iteritems():
        fc_result[key] = []
        id = key
        for i in xrange(0,5):
            d = {
                'name': keys[i]+NAME_PREFIX + id,
                'call_back': callback_funcs[i],
                'time_max': 90,
                'value_type': value_types[i],
                'units': 'C',
                'slope': 'both',
                'format': formats[i],
                'description': descripts[i],
                'groups': 'flashcache'
            }
            descriptors.append(d)
    return descriptors
def metric_cleanup():
    pass
if __name__ == '__main__':
    #get_dev_map_to_disk()
    #get_osd_map_to_dev()
    descriptors = metric_init({})
    for d in descriptors:
        v = d['call_back'](d['name'])
        print ('value for %s is '+d['format']) % (d['name'], v)
