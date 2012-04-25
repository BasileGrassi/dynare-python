"""
All informations about this module.
I can use complex formulas: :math:`n_{\mathrm{offset}} = \sum_{k=0}^{N-1} s_k n_k`
"""

import numpy as np


def deterministic_residuals(s, x, interp, f, g, sigma, parms):
    """
    :param s:
    :param x:
    :param interp:
    :param f:
    :param g:
    :param sigma:
    :param parms:
    :return:
    """

    n_x = x.shape[0]
    n_g = x.shape[1]
    n_e = sigma.shape[0]
    interp.fit_values(x)
    dummy_epsilons = np.zeros((n_e,n_g))
    [snext] = g(s,x,dummy_epsilons,parms)[:1]
    [xnext] = interp.interpolate(snext)[:1]
    [val] = f(s,x,snext,xnext,dummy_epsilons,parms)[:1]
    return val


def stochastic_residuals(s, x, dr, f, g, parms, epsilons, weights):
    n_draws = epsilons.shape[1]
    [n_x,n_g] = x.shape
    dr.fit_values(x)
    ss = np.tile(s, (1,n_draws))
    xx = np.tile(x, (1,n_draws))
    ee = np.repeat(epsilons, n_g , axis=1)
    [ssnext] = g(ss,xx,ee,parms)[:1]
    [xxnext] = dr.interpolate(ssnext)[:1]
    [val] = f(ss,xx,ssnext,xxnext,ee,parms)[:1]

    res = np.zeros( (n_x,n_g) )
    for i in range(n_draws):
        res += weights[i] * val[:,n_g*i:n_g*(i+1)]
    return res


def stochastic_residuals_2(s, theta, dr, f, g, parms, epsilons, weights, shape, no_deriv=False):

    n_t = len(theta)
    dr.theta = theta.copy().reshape(shape)
    #    [x, x_s, x_theta] = dr.interpolate(s, with_theta_deriv=True)
    n_draws = epsilons.shape[1]
    [n_s,n_g] = s.shape
    ss = np.tile(s, (1,n_draws))
    [xx, xx_s, xx_theta] = dr.interpolate(ss, with_theta_deriv=True) # should repeat theta instead
    n_x = xx.shape[0]
    #    xx = np.tile(x, (1,n_draws))
    ee = np.repeat(epsilons, n_g , axis=1)
    [SS, SS_ss, SS_xx, SS_ee] = g(ss, xx, ee, parms)
    [XX, XX_SS, XX_t] = dr.interpolate(SS, with_theta_deriv=True)
    [F, F_ss, F_xx, F_SS, F_XX, F_ee] = f(ss, xx, SS, XX, ee, parms)


    res = np.zeros( (n_x,n_g) )
    for i in range(n_draws):
        res += weights[i] * F[:,n_g*i:n_g*(i+1)]

    if no_deriv:
        return res

    from dolo.numeric.serial_operations import serial_multiplication as stm
    SS_theta = stm( SS_xx, xx_theta)
    XX_theta = stm( XX_SS, SS_theta) + XX_t
    dF = stm(F_xx, xx_theta) + stm( F_SS, SS_theta) + stm( F_XX , XX_theta)
    dres = np.zeros( (n_x,n_t,n_g))
    for i in range(n_draws):
        dres += weights[i] * dF[:,:,n_g*i:n_g*(i+1)]
    return [res,dres.swapaxes(1,2)]

def stochastic_residuals_3(s, theta, dr, f, g, parms, epsilons, weights, shape, no_deriv=False):

    import numpy
    n_t = len(theta)
    dr.theta = theta.copy().reshape(shape)
    #    [x, x_s, x_theta] = dr.interpolate(s, with_theta_deriv=True)
    n_draws = epsilons.shape[1]
    [n_s,n_g] = s.shape
    [x, x_s, x_theta] = dr.interpolate(s, with_theta_deriv=True) # should repeat theta instead
    n_x = x.shape[0]
    #    xx = np.tile(x, (1,n_draws))
    #ee = np.repeat(epsilons, n_g , axis=1)
    #
    from dolo.numeric.serial_operations import serial_multiplication as stm
    #
    res = np.zeros( (n_x,n_g) )
    dres = np.zeros( (n_x,n_t,n_g))
    for i in range(n_draws):
        tt = [epsilons[:,i:i+1]]*n_g
        e = numpy.column_stack(tt)
        [S, S_s, S_x, S_e] = g(s, x, e, parms)
        [X, X_S, X_t] = dr.interpolate(S, with_theta_deriv=True)
        [F, F_s, F_x, F_S, F_X, F_e] = f(s, x, S, X, e, parms)
        res += weights[i] * F
        S_theta = stm(S_x, x_theta)
        X_theta = stm(X_S, S_theta) + X_t
        dF = stm(F_x, x_theta) + stm( F_S, S_theta) + stm( F_X , X_theta)
        dres += weights[i] * dF
    return [res,dres.swapaxes(1,2)]

def step_residual(s, x, dr, f, g, parms, epsilons, weights, x_bounds=None, serial_grid=True, with_derivatives=True):
    n_draws = epsilons.shape[1]
    [n_x,n_g] = x.shape
    from dolo.numeric.serial_operations import serial_multiplication as stm
    ss = np.tile(s, (1,n_draws))
    xx = np.tile(x, (1,n_draws))
    ee = np.repeat(epsilons, n_g , axis=1)
    if with_derivatives:
        [ssnext, g_ss, g_xx] = g(ss,xx,ee,parms)[:3]
        [xxnext, xxold_ss] = dr.interpolate(ssnext)[:2]
        if x_bounds:
            [lb,ub] = x_bounds(ssnext, parms)
            xxnext = np.maximum(np.minimum(ub,xxnext),lb)

        [val, f_ss, f_xx, f_ssnext, f_xxnext] = f(ss,xx,ssnext,xxnext,ee,parms)[:5]
        dval = f_xx + stm(f_ssnext, g_xx) + stm(f_xxnext, stm(xxold_ss, g_xx))

        res = np.zeros( (n_x,n_g) )
        for i in range(n_draws):
            res += weights[i] * val[:,n_g*i:n_g*(i+1)]

        dres = np.zeros( (n_x,n_x,n_g) )
        for i in range(n_draws):
            dres += weights[i] * dval[:,:,n_g*i:n_g*(i+1)]

        if not serial_grid:
            dval = np.zeros( (n_x,n_g,n_x,n_g))
            for i in range(n_g):
                dval[:,i,:,i] = dres[:,:,i]
        else:
            dval = dres

        return [res, dval]
    else:
        [ssnext] = g(ss,xx,ee,parms,derivs=False)[:1]
        [xxnext] = dr.interpolate(ssnext)[:1]
        if x_bounds:
            [lb,ub] = x_bounds(ssnext, parms)
            xxnext = np.maximum(np.minimum(ub,xxnext),lb)

        [val] = f(ss,xx,ssnext,xxnext,ee,parms,derivs=False)[:1]

        res = np.zeros( (n_x,n_g) )
        for i in range(n_draws):
            res += weights[i] * val[:,n_g*i:n_g*(i+1)]

        return [res]


#f = model_fun['f']
#g = model_fun['g']
def test_residuals(s,dr, f,g,parms, epsilons, weights):
    n_draws = epsilons.shape[1]

    n_g = s.shape[1]
    x = dr(s)
    n_x = x.shape[0]

    ss = np.tile(s, (1,n_draws))
    xx = np.tile(x, (1,n_draws))
    ee = np.repeat(epsilons, n_g , axis=1)

    [ssnext] = g(ss,xx,ee,parms)[:1]
    xxnext = dr(ssnext)
    [val] = f(ss,xx,ssnext,xxnext,ee,parms)[:1]

    errors = np.zeros( (n_x,n_g) )
    for i in range(n_draws):
        errors += weights[i] * val[:,n_g*i:n_g*(i+1)]

    squared_errors = np.power(errors,2)
    std_errors = np.sqrt( np.sum(squared_errors,axis=0)/len(squared_errors) )

    return std_errors


def time_iteration(grid, interp, xinit, f, g, parms, epsilons, weights, x_bounds=None, options={}, serial_grid=True, verbose=True, method='lmmcp', maxit=500, nmaxit=5, backsteps=10, hook=None):

    from dolo.numeric.solver import solver
    from dolo.numeric.newton import newton_solver

    if serial_grid:
        #fun = lambda x: step_residual(grid, x, interp, f, g, parms, epsilons, weights, x_bounds=x_bounds, with_derivatives=False)[0]
        #dfun = lambda x: step_residual(grid, x, interp, f, g, parms, epsilons, weights, x_bounds=x_bounds)[1]
        fun = lambda x: step_residual(grid, x, interp, f, g, parms, epsilons, weights, x_bounds=x_bounds)
    else:
        fun = lambda x: step_residual(grid, x, interp, f, g, parms, epsilons, weights, x_bounds=x_bounds, serial_grid=False, with_derivatives=False)[0]
        dfun = lambda x: step_residual(grid, x, interp, f, g, parms, epsilons, weights, x_bounds=x_bounds, serial_grid=False)[1]

    #
    tol = 1e-8
    ##
    import time
    t1 = time.time()
    err = 1
    x0 = xinit
    it = 0

    verbit = True if verbose=='full' else False

    if x_bounds:
        [lb,ub] = x_bounds(grid,parms)
    else:
        lb = None
        ub = None

    if verbose:
        s = "|Iteration\t|\tStep\t\t\t|\tTime (s)\t|"
        nnn = len(s.replace('\t',' '*4))
        print('-'*nnn)
        print(s)
        print('-'*nnn)



    while err > tol and it < maxit:
        t_start = time.time()
        it +=1
        interp.fit_values(x0)

        if serial_grid:
            [x,nit] = newton_solver(fun,x0,lb=lb,ub=ub,infos=True, backsteps=backsteps, maxit=nmaxit)
        else:
            x = solver(fun, x0, lb=lb, ub=ub, method=method, jac=dfun, verbose=verbit, options=options)
            nit = 0
            # we restrict the solution to lie inside the boundaries
        if x_bounds:
            x = np.maximum(np.minimum(ub,x),lb)
        #        res = abs(fun(x)).max()
        err = abs(x-x0).max()
        t_finish = time.time()
        elapsed = t_finish - t_start
        if verbose:
            print("\t\t{}\t|\t{:e}\t|\t{:f}\t|\t{}".format(it,err,elapsed,nit))
        x0 = x0 + (x-x0)
        if hook:
            hook(interp,it,err)
        if False in np.isfinite(x0):
            print('iteration {} failed : non finite value')
            return [x0, x]

    if it == maxit:
        import warnings
        warnings.warn(UserWarning("Maximum number of iterations reached"))


    t2 = time.time()
    print('Elapsed: {}'.format(t2 - t1))

    return interp
