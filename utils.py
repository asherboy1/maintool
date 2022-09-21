from __future__ import print_function

import decimal
import requests
from collections import abc
from pathlib import Path
from prettytable import PrettyTable
from robot.api import logger
import json
import re
import traceback
import six
import codecs
from HTMLTable import HTMLTable
from settings import *
from base64 import b64encode
from datetime import datetime

from robot.utils.dotdict import DotDict

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        super().default(o)

class JsonEncoderMixin(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.strftime("%Y-%m-%d %H:%M:%S")
        else:
            return json.JSONEncoder.default(self, o)

NUMBER_TYPES = list(six.integer_types) + [float]


class Table:
    def __init__(self, headers, rows, name=None):
        self.table = HTMLTable(caption=name)
        self.headers = headers
        self.rows = rows
        if not isinstance(self.headers, tuple):
            raise TypeError('headers为tuple')
    
    def __set_style(self):
        self.table.caption.set_style(caption_style)
        self.table.set_style(table_style)
        self.table.set_cell_style(cell_style)
        self.table.set_header_cell_style(header_cell_style)
        self.table.set_header_row_style(header_row_style)
    
    def render(self):
        self.table.append_data_rows(self.rows)
        self.table.append_header_rows((self.headers,))
        self.__set_style()
        return self
    
    def show(self):
        logger.info(self.table.to_html(), html=True)

def read(file_path:str) -> tuple:
    """
    二进制读文件。会默认输入绝对路径，如果路径不存在就会按照相对路径去寻找。
    :param file_path 文件绝对路径或者相对路径
    :return:返回元组（文件名，b'文件内容'）

    """
    file_path = file_path if Path(file_path).exists() else Path.cwd() / file_path
    
    if not Path(file_path).exists():
        raise FileNotFoundError(file_path)
    
    with open(file_path, 'rb') as f:
        return Path(file_path).name, f.read()

def img2base64(img_path: str) -> str:
    """
    将图片转为base64字符串
    :param img_path 图片路径
    :return: img的base64串
    """
    with open(img_path, 'rb') as img:
        return b64encode(img.read()).decode('utf-8')

def _print(*args, kw=None):
    """
    表格显示请求信息和响应信息
    """
    _format = lambda x: x[:512] + (x[512:] and '...')
    for ob in args:
        if isinstance(ob, abc.Mapping):
            table = PrettyTable(['参数', 'Request'])
            for k, v in ob.items():
                table.add_row([k, _format(str(v))])
        elif isinstance(ob, requests.Response):
            table = PrettyTable(['参数', 'Response'])
            table.align = 'l'
            for k, v in ob.__dict__.items():
                if not kw or k in kw:
                    table.add_row([k, _format(v.decode('utf-8')) if isinstance(v, bytes) else v])
        else:
            raise TypeError
        
        logger.info(table.get_string())

class NamingMethod:
    """
    1.驼峰命名法 myName
    2.帕斯卡命名法 Pascal 
    MyName
    3.蛇形命名法 Snake
    my_name
    """

    @staticmethod
    def __any2lw(x):
        lw = x.split('_')
        if len(lw) > 1:
            return map(lambda x:x.lower(), lw)
        pieces = re.split('([A-Z])', x)
        if pieces[0]:
            pieces = [''] + pieces
        else:
            pieces = pieces[1:]
        
        return [pieces[i].lower() + pieces[i + 1] for i in range(0, len(pieces), 2)]

    @classmethod
    def any2Snake(cls, x):
        return '_'.join(cls.__any2lw(x))
    
    @classmethod
    def any2Pascal(cls, x):
        return ''.join(map(lambda x: x.capitalize(), cls.__any2lw(x)))
    
    @classmethod
    def any2CamelCase(cls, x):
        return x[0].lower() + cls.any2Pascal(x)[1:]


class Compare(object):
    def __init__(self, print_before=True, float_fuzzy_digits=0, strict_number_type=False, subject_to_expect=False):
        self.print_before = print_before
        self.float_fuzzy_digits = float_fuzzy_digits
        self.strict_number_type = strict_number_type
        self._res = None
        self._ignore_list_seq = None
        self._re_compare = True
        self._ignore_path = None
        self._omit_path = None
        self._handle = print
        self._ignore_int = False
        self.subject_to_expect = subject_to_expect

        # self.table = Table(name='结果比对', headers=('参数', '值'),
        #                                                 rows=(
        #                                                     ('status_code', r.status_code),
        #                                                     ('content', content),
        #                                                     ('编码格式', r.encoding)
        #                                                 ))

    @staticmethod
    def _tuple_append(t, i):
        return tuple(list(t) + [six.text_type(i)])
    
    @staticmethod
    def _to_unicode_if_string(strlike):
        if type(strlike) == six.binary_type:
            try:
                return strlike.decode('utf-8')
            except UnicodeDecodeError:
                raise ValueError("decode string {} failed, may be local encoded".format(repr(strlike)))
        else:
            return strlike


    @staticmethod
    def _to_list_if_tuple(listlike):
        if type(listlike) == tuple:
            return list(listlike)
        else:
            return listlike
    
    @staticmethod
    def _to_dict_if_DotDict(dictlike):
        if isinstance(dictlike, DotDict):
            return dict(dictlike)
        else:
            return dictlike

    def _common_warp(self, anylike):
        return self._to_dict_if_DotDict(self._to_list_if_tuple(self._to_unicode_if_string(anylike)))
    
    def _fuzzy_float_equal(self, a, b):
        if self.float_fuzzy_digits:
            return abs(a - b) < 10 ** (-self.float_fuzzy_digits)
        else:
            return a == b

    @staticmethod
    def _modify_a_key(dic, from_key, to_key):
        assert not any([type(to_key) == type(exist_key) and to_key == exist_key for exist_key in dic.keys()]), 'cant change the key due to key conflicts'
        # cant use in here to_key in dic.keys(),because u"a" in ["a"] ==True
        dic[to_key] = dic.pop(from_key)


    def _fuzzy_number_type(self, value):
        if not self.strict_number_type:
            type_dict = {x: float for x in six.integer_types}
        else:
            type_dict = {x: int for x in six.integer_types}
        res = float if isinstance(value, decimal.Decimal) else type(value)
        return type_dict.get(res, res)

    def _turn_dict_keys_to_unicode(self, dic):
        keys = dic.keys()
        modifiers = []
        for key in keys: #constant
            if type(key) == six.binary_type:
                modifiers.append((key, self._to_unicode_if_string(key)))
            else:
                assert type(key) == six.text_type, 'key {} must be string or unicode in dict {}'.format(key, dic)
        
        for from_key, to_key in modifiers:
            self._modify_a_key(dic, from_key, to_key)
    
    def _self_false(self):
        self._res = False


    @staticmethod
    def _escape(s):
        if r'\x' in s:
            s = s.decode('string-escape') if six.PY2 else codecs.escape_decode(s)[0].decode('utf-8')
        if r'\u' in s:
            s = s.decode('unicode-escape') if six.PY2 else s.encode().decode('unicode-escape')
        if type(s) == six.binary_type:
            s = s.decode('utf-8')
        return s
    
    # differnent_print_method
    def _different_type(self, a, b, root):
        self._self_false()
        self._handle("【数据类型不同】位于/{}".format("/".join(root)))
        self._handle("a {}: ".format(type(a)) + repr(a))
        self._handle("b {}: ".format(type(b)) + repr(b))
    
    def _different_length(self, a, b, root):
        self._self_false()
        self._handle("【列表长度不同】位于 /{}".format("/".join(root)))
        self._handle("len(a)={} : ".format(len(a)) + repr(a))
        self._handle("len(b)={} : ".format(len(b)) + repr(b))

    def _different_value(self, a, b, root, set_false=True):
        if set_false:
            self._self_false()
        self._handle("【值不同】位于 /{}".format("/".join(root)))
        self._handle("a: " + repr(a))
        self._handle("b: " + repr(b))
    
    def _list_item_not_found(self, ele, which, root):
        self._self_false()
        self._handle("列表{}位于/{}".format(which, "/".join(root)))
        self._handle("有以下元素，而另一个列表没有:")
        self._handle(repr(ele))
    
    def _list_freq_not_match(self, root, aplace, bplace, ele, counta, countb):
        self._self_false()
        self._handle("列表a位于/{}，索引|{}，和b位于索引|{}元素相比有不同的个数:".format("/".join(root), aplace, bplace))
        self._handle("列表a中的{}数量：{}".format(ele, counta))
        self._handle("列表b中的{}数量：{}".format(ele, countb))
    
    def _dict_key_not_found(self, keys, which, root):
        self._self_false()
        self._handle("字典{} 位于 /{}".format(which, "/".join(root)))
        self._handle("有另一个字典没有的值：")
        self._handle(keys)
    
    # internal compare methods
    def _list_comp(self, a, b, root, printdiff):
        if len(a) != len(b):
            if not printdiff:
                return False
            self._different_length(a, b, root)
            found_b = [False] * len(b)

            for i, a_i in enumerate(a):
                found = False
                for j, b_j in enumerate(b):
                    if self._common_comp(a_i, b_j, printdiff=False):
                        found_b[j] = True
                        found = True
                        break
                if not found:
                    buff = self._tuple_append(root, i)
                    self._list_item_not_found(a_i, "a", buff)

            found_a = [False] * len(a)
            for j ,b_j in enumerate(b):
                found = False
                for i,a_i in enumerate(a):
                    if self._common_comp(a_i, b_j, printdiff=False):
                        found_a[i] = True
                        found = True
                        break
                if not found:
                    buff = self._tuple_append(root, j)
                    self._list_item_not_found(b_j, "b", buff)
            return
        
        if not self._ignore_list_seq:
            for i in range(min(len(a), len(b))):
                buff = self._tuple_append(root, i)
                if not self._common_comp(a[i], b[i], buff, printdiff):
                    if not printdiff:
                        return False
        else:
            counts_a = [[0, None] for _ in range(len(a))]
            counts_b = [[0, None] for _ in range(len(a))]
            need_to_compare_number = True

            for i in range(len(a)):
                for j in range(len(a)):
                    buff = self._tuple_append(root, len(a) * 10)
                    if self._common_comp(a[i], b[j], buff, printdiff=False):
                        counts_a[i][1] = j
                        counts_a[i][0] += 1
                    if self._common_comp(b[i], a[j], buff, printdiff=False):
                        counts_b[i][1] = j
                        counts_b[i][0] += 1    

                if not counts_a[i][0]:
                    if not printdiff:
                        return False
                    need_to_compare_number = False
                    buff = self._tuple_append(root, i)
                    self._list_item_not_found(a[i], "a", buff)
                
                if not counts_b[i][0]:
                    if not printdiff:
                        return False
                    need_to_compare_number = False
                    buff = self._tuple_append(root, i)
                    self._list_item_not_found(b[i], "b", buff)

            if need_to_compare_number:
                for i in range(len(counts_a)):
                    counta, place = counts_a[i]
                    countb = counts_b[place][0]
                    if countb != counta and counts_b[place][1] == i:
                        if not printdiff:
                            return False
                        self._list_freq_not_match(root, i, place, a[i], countb, counta) # nedd to swap counter here :)
                    
        if not printdiff:
            return True

    def _dict_comp(self, a, b, root, printdiff):
        self._turn_dict_keys_to_unicode(a)
        self._turn_dict_keys_to_unicode(b)

        if self._omit_path:
            omit_dict = {}
            for x in self._omit_path:
                pre, tat = x.split(u"/")[1:-1], x.split(u"/")[-1]
                for i, v in enumerate(pre):
                    if v == u"*" and i <len(root):
                        pre[i] = root[i]
                pre = tuple(pre)
                if pre not in omit_dict:
                    omit_dict[pre] = [tat]
                else:
                    omit_dict[pre].append(tat)
            if root in omit_dict:
                a = {k: v for k, v in a.items() if k not in omit_dict[root]}
                b = {k: v for k, v in b.items() if k not in omit_dict[root]}

        ak = a.keys()
        bk = b.keys()
        diffak = [x for x in ak if x not in bk]
        diffbk = [x for x in bk if x not in ak]
        if self.subject_to_expect:
            if diffbk:
                if not printdiff:
                    return False
                self._dict_key_not_found(diffbk, "a", root)
        else:
            if diffak:
                if not printdiff:
                    return False
                self._dict_key_not_found(diffak, "a", root)
            if diffbk:
                if not printdiff:
                    return False
                self._dict_key_not_found(diffak, "b", root)
        samekeys = [x for x in bk if x in ak]

        for key in samekeys:
            buff = self._tuple_append(root, key)
            if not self._common_comp(a[key], b[key], buff, printdiff):
                if not printdiff:
                    return False
        
        if not printdiff:
            return True
    
    def _common_comp(self, a, b, root=(), printdiff=True):
        if self._ignore_path:
            current_path = u"/{}".format(u"/".join(root))

            for ignore_item in self._ignore_path:
                if ignore_item[0] == u"^" or ignore_item[-1] == u"$":
                    find = re.findall(ignore_item, current_path)
                    assert len(find < 2) , "error"
                    if find and find[0] == current_path:
                        return True
                else:
                    if u"/{}".format(u"/".join(root)) == ignore_item:
                        return True
        
        a = self._common_warp(a)
        b = self._common_warp(b)

        if self._fuzzy_number_type(a) != self._fuzzy_number_type(b):
            if self._fuzzy_number_type(a) is bool and self._fuzzy_number_type(b) is str or self._fuzzy_number_type(b) is bool and self._fuzzy_number_type(a) is str:
                if not self._value_comp(str(a).lower(), str(b).lower(), printdiff):
                    if not printdiff:
                        return False
                    self._different_value(a, b, root)
                return True

            if self._fuzzy_number_type(a) is str and self._fuzzy_number_type(b) in [int, float] or self._fuzzy_number_type(b) is str and self._fuzzy_number_type(a) in [int, float]:
                if self._ignore_int:
                    if not self._value_comp(float(a), float(b), printdiff):
                        if not printdiff:
                            return False
                        self._different_value(a, b, root)
                    return True

            if not printdiff:
                return False
            self._different_type(a, b , root)
            return
        
        if type(a) not in [dict, list]:
            if not self._value_comp(a, b, printdiff):
                if not printdiff:
                    self._different_value(a, b, root[1:], set_false=False)
                    return False
                self._different_value(a, b, root)
            elif not printdiff:
                return True
            return
        
        if type(a) == list:
            return self._list_comp(a, b, root, printdiff)
        
        if type(a) == dict:
            return self._dict_comp(a, b, root, printdiff)
        
        raise TypeError("error here")

    def _value_comp(self, a, b, printdiff=True): #base comp
        if not self._re_compare or type(a) != six.text_type or type(b) != six.text_type:
            if (type(a) == float and type(b) in NUMBER_TYPES) or (type(b) == float and type(a) in NUMBER_TYPES):
                return self._fuzzy_float_equal(a, b)
            else:
                return a == b
        else:
            a_is_re = len(a) > 0 and (a[0] == u"^" or a[-1] == u"^")
            b_is_re = len(b) > 0 and (b[0] == u"^" or b[-1] == u"^")  # prevents index out of range error
            if not a_is_re and not b_is_re:
                return a == b
            assert not (a_is_re and b_is_re), 'cant comp two regular expressions'
            if b_is_re:
                a, b = b, a
            find = re.findall(a, b)
            assert len(find) < 2, 'error here'
            if not find:
                if printdiff:
                    self._handle('re comp failed, empty match, see next line')
                return False
            if not find[0] == b:
                if printdiff:
                    self._handle('re comp failedm found {}, expect {}, see next line'.format(find[0], b))
                return False
            return True
    
    # method
    def compare(self, a, b, ignore_list_seq=True, re_compare=True, ignore_path=None, callback=print, strict_type=False,
                float_fuzzy_digits=None, strict_number_type=None, omit_path=None, ignore_int=False, subject_to_expect=False):
        self._handle = callback
        self.ignore_int = ignore_int
        self.subject_to_expect = subject_to_expect
        flag = False # transferred str to object, need recursion

        if type(a) in [six.text_type, six.binary_type]:
            json_loaded_a = json.loads(a)
            flag = True
        else:
            json_loaded_a = a
        if type(b) in (six.text_type, six.binary_type):
            json_loaded_b = json.loads(b)
            flag = True
        else:
            json_loaded_b = b
        if flag:
            return self.compare(json_loaded_a, json_loaded_b, ignore_list_seq, re_compare, ignore_path, callback,
                                strict_type, float_fuzzy_digits, strict_number_type, omit_path)
        
        if strict_type:
            try:
                json.dumps(a, ensure_ascii=False)
                json.dumps(b, ensure_ascii=False)
            except TypeError:
                self._handle(traceback.format_exc())
                raise TypeError("unsupported type found durng strict json check")
        
        self._res = True
        self._ignore_list_seq = ignore_list_seq
        self._re_compare = re_compare
        self._ignore_path = None if ignore_path is None else [self._to_unicode_if_string(path) for path in ignore_path]
        self._omit_path = None if omit_path is None else [self._to_unicode_if_string(path) for path in omit_path]

        if self._ignore_path:
            assert all([path[0] ==  u"/" or u"(/" in path for path in self._ignore_path]), "invalid ignore path"
        if self._omit_path:
            assert all([path[0] == u"/" and path.split(u"/")[-1] not in (u"", u"*") and not path.split(u"/")[-1].isdigit() for path in self._omit_path]), "invalid omit path"
        
        if float_fuzzy_digits is not None:
            self.float_fuzzy_digits = float_fuzzy_digits
        if strict_number_type is not None:
            self.strict_number_type = strict_number_type
        
        if self.print_before:
            self._handle(self._escape("a is {}".format(a)))
            self._handle(self._escape("b is {}".format(b)))
            self._handle("ignore_list_seq = {}, re_compare = {}, ignore_path = {}, omit_path = {}, float_fuzzy_digits =  " "{}".format(ignore_list_seq, re_compare, ignore_path, omit_path, self.float_fuzzy_digits))

        self._common_comp(a, b)
        return self._res

if __name__ == "__main__":
    pass














































































































































    





































        




























        