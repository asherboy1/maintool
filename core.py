from ast import Compare
from asyncore import read
from http.client import responses
from msilib import Table
import os
from collections import abc
from posixpath import split
from tabnanny import check
from urllib import response
import requests
import json
from utils import _print, read, NamingMethod, Compare, Table
from robot.api import logger
from robot.api.deco import not_keyword
from robot.utils.dotdict import DotDict
import jsonpath
from jsonpath_ng import parse
from db import ConnectMySQL
from copy import deepcopy
from settings import *

@not_keyword
def xrequest(method, url, content_type=None, query=None, params=None, datas=None, files=None, cookie=None, headers=None, is_print_request=True, is_print_response=True) -> requests.Response:
    if method.upper() not in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
        raise NotImplemented(f"请求方法【{method}】填写错误！")
    
    cookie = {} if cookie is None else cookie
    headers = {} if headers is None else headers
    datas = None if datas is None else datas
    content_type = 'applocation/json' if content_type is None else content_type #form_data不能指定content_type,否则header中不会生产boundary

    headers.update({'Content-Type': content_type})
    _headers = deepcopy(headers)
    _datas = deepcopy(datas)

    if content_type == 'application/json':
        datas = json.dumps(datas)
        _datas = json.dumps(_datas, ensure_ascii=False)
    
    #处理多文件上传
    __files = {} if files is None else files
    _files = {}
    if not isinstance(__files, abc.Mapping):
        raise TypeError
    else:
        for k, v in __files.items():
            if isinstance(v, abc.Mapping):
                for i in v:
                    _files.append((k, read(i)))
            # TODO 指定参数为空
            elif v is None:
                _files.append((k, None))
            else:
                raise NotImplemented
    
    if content_type == 'multipart/form_data':
        headers.pop("Content_Type")
        # TODO 保留原始报文用于日志
        if datas and not files:
            datas, _files = None, {k: (None, v) for k, v in datas.items()}
            _datas = None
    
    if params is not None:
        # TODO 使用format_map替换
        url = os.path.dirname(url) if params == {} and "{" in os.path.basename(url) else url.format(**params) # 处理url参数，默认只有一个参数

    if not isinstance(cookie, abc.Mapping):
        try:
            cookie = {i.spllit("=")[0].strip(): i.split("=")[1].strip() for i in cookie.split(";")}
        except IndexError:
            raise TypeError
        
    params_dict = {
        'url': url,
        'method': method,
        'params': query,
        'files': _files,
        'data': datas,
        'headers': headers,
        'cookies': cookie
    }

    # _print(params_dict)
    r = requests.request(**params_dict)
    # _print(r, kw=['status_code', '_content'])
    if is_print_request:
        Table(name="请求", headers=('参数', "值"),
            rows=(
                ('url', r.url),
                ('method', method),
                ('headers', _headers),
                ('cookies', cookie),
                ('data', _datas),
                ('files', _files)
            )
            ).render().show()
    
    try:
        content = r.content.decode('utf-8')
    except UnicodeDecodeError:
        content = r.content
    if is_print_response:
        Table(name='响应', headers=('参数', '值'),
            row=(
                ('status_code', r.status_code),
                ('content', content),
                ('编码格式', r.encoding),
            )
        ).render().show()

    return r


@not_keyword
def xcheck(r, *args, **kwargs):
    def _assert(t, k, v):
        find = jsonpath.jsonpath(r, k)
        if not find:
            raise LookupError(f'jsonpath搜索失败，检查jsonpath【{k}】,也有课需检查结果中不存在此字段')
        
        find = find[0] if len(find) == 1 else find
        t.rows.append((k, v, find))

        # TODO 代码重构
        if isinstance(r, requests.Response):
            try:
                r = r.json()
            except Exception as e:
                raise TypeError(f'请检查参数输入,{e}')
        
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except ValueError:
                raise TypeError(f'响应输入json格式错误')
        
        if isinstance(r, abc.Mapping):
            check_table = Table(name='检查结果',headers=('检查项', '预期结果', '实际结果'), row=[])
            if args:
                for i in range(0, len(args), 2):
                    try:
                        _assert(check_table, args[i], args[i + 1])
                    except IndexError:
                        raise TypeError('检查参数')
            if kwargs:
                for k, v in kwargs.items():
                    _assert(check_table, k, v) 

            # TODO 代码重构
            check_table.rows = tuple(check_table.rows)
            check_table.render()
            error_list = []
            for row in check_table.table.iter_data_rows():
                if row[1].value != row[2].value:
                    row[1].value = f"{type(row[1].value)}{row[1].value}"
                    row[2].value = f"{type(row[2].value)}{row[2].value}"
                    row.set_style(error_rows_style)
                    error_list.apped(row)
                else:
                    row[1].value = str(row[1].value)
                    row[2].value = str(row[2].value)
            check_table.show()
            if error_list:
                for row in error_list:
                    logger.error(f"{row[1].value} != {row[2].value}")
                raise AssertionError("检查十八，请检查日志了解详情")
            return True
        else:
            raise TypeError('响应输入格式错误，请检查输入内容是否符合要求')


@not_keyword
def xcompare(base, expect, **kwargs):
    # TODO 时间转换
    """
    比对两组数据

    :param base:输入数据

    :param expect:期望结果

    :return:None
    """

    def _format(input):
        if isinstance(input, DotDict):
            return dict(input)
        elif isinstance(input, str):
            if kwargs.pop('convert_bool', False):
                true, false = True, False
            return eval(input)
        else:
            return input

    base, expect = _format(base), _format(expect)

    naming_method = kwargs.pop('naming_method', False)
    replace_items = kwargs.pop('replace_items', None)

    def replace_key(raw_data, path_of_key, replace_to):
        keys = str(path_of_key),split('.')
        tmp = raw_data
        for k in keys[:-1]:
            if '[' and ']' in k:
                k = int(k.strip('[').strip(']'))
            tmp = tmp[k]
        tmp[replace_to] = tmp.pop(keys[-1])
        return raw_data
    
    if replace_items:
        if not isinstance(replace_items, abc.Mapping):
            raise TypeError
        else:
            for k, v in replace_items.items():
                r = parse(k).find(expect)
                if len(r) == 1:
                    expect = replace_key(expect, r[0].full_path, v)
                else:
                    raise ValueError(f'指定替换的key不存在或不唯一:{r}')
    
    if naming_method:
        if not callable(naming_method):
            try:
                naming_method = getattr(NamingMethod, naming_method)
            except:
                   raise ValueError(f'命名方法{naming_method}不在any2snke/any2pascal/any2camecase中')

        def replace_key(data, naming_method):
            _data = deepcopy(data)
            
            def _replace(a):
                if isinstance(a, list):
                    for i in a:
                        _replace(i)
                if isinstance(a, dict):
                    _a = deepcopy(a)
                    for k , v in _a.items():
                        _v = a.pop(k)
                        a[naming_method(k)] = v
                        if type(_v) in [list, dict]:
                            _replace(_v)
            
            _replace(_data)

            return _data
            
        expect = replace_key(data=expect, naming_method=naming_method)
        
    return Compare(print_before=True).compare(base, expect, **kwargs)


@not_keyword
def xsql(db, sql):
    with ConnectMySQL(db) as db:
        logger.info(sql)
        # TODO 执行sum语句换返回Decimal类型
        db.cursr.execute(sql)
        db.conn.commit()
        # TODO update操作返回值
        return list(db.cursor.fetchall())






















































                



















































