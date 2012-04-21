from __future__ import division

import unittest


class  TestInterpolation(unittest.TestCase):

    def test_2d_interpolation(self):
        import numpy
        from dolo.numeric.interpolation import RectangularDomain, SplineInterpolation, LinearTriangulation, TriangulatedDomain
        from dolo.numeric.smolyak import SmolyakGrid
        smin = [-2,-2]
        smax = [2,2]
        orders = [5,5]
        orders_ref = [100,100]
        l= 6
        bounds = numpy.row_stack([smin,smax])
        recdomain = RectangularDomain( smin, smax, orders )
        tridomain = TriangulatedDomain( recdomain.grid )
        recdomain_ref = RectangularDomain( smin, smax, orders_ref )
        smolyakgrid = SmolyakGrid( bounds, l)


        fun = lambda x: 1.0/numpy.sqrt(2*numpy.pi)*numpy.exp( -( numpy.square(x[0:1,:]) + numpy.square(x[1:2,:]) ) / 2.0 )

        values_rec = fun(recdomain.grid)
        values_smol = fun(smolyakgrid.grid)

        interp_rec = SplineInterpolation(smin,smax,orders)
        interp_smol = smolyakgrid
        interp_simplex = LinearTriangulation(tridomain)

        interp_rec.fit_values(values_rec)
        interp_smol.fit_values(values_smol)
        interp_simplex.fit_values(values_rec)
        
        true_values = fun(recdomain_ref.grid).reshape(orders_ref)
        interpolated_values_spline = interp_rec(recdomain_ref.grid).reshape(orders_ref)
        interpolated_values_simplex = interp_simplex(recdomain_ref.grid).reshape(orders_ref)
        interpolated_values_smolyak = interp_smol(recdomain_ref.grid).reshape(orders_ref)

#
#        from mayavi import mlab
#        mlab.figure(bgcolor=(1.0,1.0,1.0))
#        #mlab.surf(abs(interpolated_values_smolyak-true_values),warp_scale="auto")
##        mlab.surf(abs(interpolated_values_spline-true_values),warp_scale="auto")
#        mlab.surf(abs(interpolated_values_simplex-true_values),warp_scale="auto")
#        mlab.colorbar()
        
if __name__ == '__main__':
    unittest.main()
    tt = TestInterpolation()
    tt.test_2d_interpolation()

