from core import xcompare

a = {
    "a" : 1,
    "b": 2
}

b = {
    "a": 1,
    "c": 3
}

print(xcompare(a, b))

class testcomp:
    @staticmethod
    def test_list_tuple():
        a = [1,2,2]
        b = [1,1,2]
        assert xcompare(a,b) is False

        a = [1,2,3]
        b = [1,3,4,5]
        assert xcompare(a,b) is False

        
        assert xcompare(a,b) is True

        a = [1, {"a":["ok","no"]} , 2]
        b = [1,2,{"a":["ok","no"]}]
        assert xcompare(a,b) is True

# testcomp.test_list_tuple()
a = [[1,2,3],[4,5,6]]
b = [[6,5,4],[3,2,1]]
print(xcompare(a,b))

a = {"a":[1,{"k":["aa"],"a":1}]}
b = {"a":[1,{"k":["bb"],"a":2}]}
print(xcompare(a,b))
print(xcompare(a,b,ignore_list_seq=False,ignore_path=["/a/1/k","/a/1/a"]))


a = {"a":[{"b":1,"c":2},{"c":4,"d":5}]}
b = {"a":[{"c":2},{"c":4}]}
print(xcompare(a,b,ignore_list_seq=False,omit_path=["/a/*/b","/a/*/d"]))

a = {"1":[1,2],"3":[4,5]}
b = {"1":[2,1],"3":[5,4]}
assert xcompare(a,b) is False