

quantization_data = '/home/pablo/Programmation/dynare-python/dolo/src/dolo/numeric/data/quantization_grids/'


def quantization_weights(N,sigma):
    import numpy
    import numpy.linalg
    assert( len(sigma.shape) == 2 )
    var = numpy.diag(sigma)
    d = sigma.shape[0]
    [w, x] = standard_quantization_weights(N,d )
    A = numpy.linalg.cholesky(sigma)
    x = numpy.dot(A, x)
    return [w,x]

def standard_quantization_weights(N,d):
    filename = quantization_data + '{0}_{1}_nopti'.format(N,d)
    import numpy

    try:
        G = numpy.loadtxt(filename)
    except Exception as e:
        raise e

    w = G[:N,0]
    x = G[:N,1:d+1]
    return [w,x.T]

if __name__ == '__main__':
    N = 8
    d = 4
    import numpy
    sigma = numpy.diag([0.01,0.01,0.01,0.01])
    [w,x] = quantization_weights(N,sigma)
    print 'w'
    print w
    print 'x'
    print x
