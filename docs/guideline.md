## Asynchronous IO
smart way to handle zmq requests
## Multiprocessing
ProcessPoolExecutor, memory manager and locks (mutex)
## Shared memory
Here is a small explanation why the threshold is handled in other way as images buffers:
Despite the fact there is a thread safe "multiprocessing.Value" class for scalars (see above), there is no class for 2D array.
Yes, there are 1D arrays available (see "multiprocessing.Array"), but they need to be handled as python arrays and not as numpy arrays.
Continuos rearrangement of them into numpy arrays and vise versa considered as bad.
In python 3.8 shared memory feature was introduced which allows to work directly with memory and use a numpy array as proxy to it.
Documentation: https://docs.python.org/3.8/library/multiprocessing.shared_memory.html
A good example: https://luis-sena.medium.com/sharing-big-numpy-arrays-across-python-processes-abf0dc2a0ab2

tl;dr: we are able to share any numpy array between processes but in little other way
