from dolo.numeric.decision_rules_states import CDR

from dolo.misc.caching import memoized

@memoized
def interim_gm( model, substitute_auxiliary, solve_systems, order):

    gm = simple_global_representation(model, substitute_auxiliary=substitute_auxiliary, allow_future_shocks=False, solve_systems=solve_systems)

    g_eqs = gm['g_eqs']
    g_args = [s(-1) for s in gm['states']] + [x(-1) for x in gm['controls']] + gm['shocks']
    f_eqs = gm['f_eqs']

    f_args = gm['states'] + gm['controls'] + [s(1) for s in gm['states']] + [x(1) for x in gm['controls']]
    p_args = gm['parameters']

    from dolo.compiler.compiling import compile_function

    g_fun = compile_function(g_eqs, g_args, p_args, order)
    f_fun = compile_function(f_eqs, f_args, p_args, order)

    return [gm,g_fun,f_fun]


def approximate_controls(model, order=1, lambda_name=None, substitute_auxiliary=False, return_dr=False, solve_systems=False):

    [gm, g_fun, f_fun] = interim_gm(model, substitute_auxiliary, solve_systems, order)

    # get steady_state
    import numpy
    [y0,x,parms] = model.read_calibration()
    parms = numpy.array(parms)

    y = y0
    #y = model.solve_for_steady_state(y0)

    sigma = numpy.array( model.covariances ).astype(float)
    states_ss = [y[model.variables.index(v)] for v in gm['states']]
    controls_ss = [y[model.variables.index(v)] for v in gm['controls']]
    shocks_ss = x

    f = f_fun( states_ss + controls_ss + states_ss + controls_ss, parms)
    g = g_fun( states_ss + controls_ss + shocks_ss, parms)

    if lambda_name:
        epsilon = 0.001
        sigma_index = [p.name for p in model.parameters].index(lambda_name)
        pert_parms = parms.copy()
        pert_parms[sigma_index] += epsilon
        g_pert = g_fun( states_ss + controls_ss + shocks_ss, pert_parms)
        sig2 = (g_pert[0] - g[0])/epsilon*2
        sig2_s = (g_pert[1] - g[1])/epsilon*2
        pert_sol = state_perturb(f, g, sigma, sigma2_correction = [sig2, sig2_s] )

    else:
        pert_sol = state_perturb(f, g, sigma )

    if order == 1:
        if return_dr:
            S_bar = numpy.array( states_ss )
            X_bar = numpy.array( controls_ss )
            # add transitions of states to the d.r.
            X_s = pert_sol[0]
            A = g[1][:,:len(states_ss)] + numpy.dot( g[1][:,len(states_ss):len(states_ss+controls_ss)], X_s )
            B = g[1][:,len(states_ss+controls_ss):]
            dr = CDR([S_bar, X_bar, X_s])
            dr.A = A
            dr.B = B

            dr.sigma = sigma
            return dr
        return [controls_ss] + pert_sol

    if order == 2:
        [[X_s,X_ss],[X_tt]] = pert_sol
        X_bar = controls_ss + X_tt/2
        if return_dr:
            S_bar = states_ss
            S_bar = numpy.array(S_bar)
            X_bar = numpy.array(X_bar)
            dr = CDR([S_bar, X_bar, X_s, X_ss])
            dr.A = g[1][:,:len(states_ss)] + numpy.dot( g[1][:,len(states_ss):len(states_ss+controls_ss)], X_s )
            dr.B = g[1][:,len(states_ss+controls_ss):]
            dr.sigma = sigma
            return dr
        return [X_bar, X_s, X_ss]


    if order == 3:
        [[X_s,X_ss,X_sss],[X_tt, X_stt]] = pert_sol
        X_bar = controls_ss + X_tt/2
        X_s = X_s + X_stt/2
        if return_dr:
            S_bar = states_ss
            return CDR([S_bar, X_bar, X_s, X_ss, X_sss])
        return [X_bar, X_s, X_ss, X_sss]
        



def simple_global_representation(self, substitute_auxiliary=False, allow_future_shocks=True, solve_systems=False):

    resp = {}
    eq_g = self['equations_groups']
    v_g = self['variables_groups']
    if 'expectation' in eq_g:
        resp['f_eqs'] = [ eq.gap for eq in  eq_g['arbitrage'] + eq_g['expectation']] # TODO: complementarity conditions
        resp['controls'] = v_g['controls'] + v_g['expectations']
    else:
        resp['f_eqs'] = [ eq.gap for eq in  eq_g['arbitrage']] # TODO: complementarity conditions
        resp['controls'] = list( v_g['controls'] )

    resp['g_eqs'] = [eq.rhs for eq in  eq_g['transition'] ]

    if 'auxiliary' in eq_g:
        if not substitute_auxiliary:
            resp['f_eqs'] += [eq.gap for eq in eq_g['auxiliary']]
            resp['controls'] += v_g['auxiliary']
        else:
            sdict = {}
            from dolo.misc.misc import timeshift
            auxies = eq_g['auxiliary']
            if 'auxiliary_2' in eq_g:
                auxies += eq_g['auxiliary_2']
            for eq in  auxies:
                sdict[eq.lhs] = eq.rhs
                sdict[eq.lhs(1)] = timeshift( eq.rhs, 1)
                sdict[eq.lhs(-1)] = timeshift( eq.rhs, -1)
            from dolo.misc.calculus import simple_triangular_solve
            sdict = simple_triangular_solve(sdict)
            resp['f_eqs'] = [eq.subs(sdict) for eq in resp['f_eqs']]
            resp['g_eqs'] = [eq.subs(sdict) for eq in resp['g_eqs']]

    if not allow_future_shocks:
        # future shocks are replaced by 0
        zero_shocks = {s(1):0 for s in self.shocks}
        resp['f_eqs'] = [ eq.subs(zero_shocks) for eq in resp['f_eqs'] ]

    if solve_systems:
        from dolo.misc.calculus import simple_triangular_solve
        system = {s: resp['g_eqs'][i] for i,s in enumerate(v_g['states'])}
        new_geqs = simple_triangular_solve(system)
        resp['g_eqs'] = [new_geqs[s] for s in v_g['states']]

    resp['states'] = v_g['states']
    resp['shocks'] = self.shocks #['shocks_ordering'] # TODO: bad
    resp['parameters'] = self.parameters #['parameters_ordering']
    return resp

def state_perturb(f_fun, g_fun, sigma, sigma2_correction=None):
    """
    Compute the perturbation of a system in the form:
    $E_t f(s_t,x_t,s_{t+1},x_{t+1})$
    $s_t = g(s_{t-1},x_{t-1},\\epsilon_t$
    
    :param f_fun: list of derivatives of f [order0, order1, order2, ...]
    :param g_fun: list of derivatives of g [order0, order1, order2, ...]
    """
    import numpy as np
    from dolo.numeric.extern.qz import qzordered
    from numpy.linalg import solve

    approx_order = len(f_fun) - 1 # order of approximation

    [f0,f1] = f_fun[:2]

    [g0,g1] = g_fun[:2]
    n_x = f1.shape[0]           # number of controls
    n_s = f1.shape[1]/2 - n_x   # number of states
    n_e = g1.shape[1] - n_x - n_s
    n_v = n_s + n_x

    f_s = f1[:,:n_s]
    f_x = f1[:,n_s:n_s+n_x]
    f_snext = f1[:,n_v:n_v+n_s]
    f_xnext = f1[:,n_v+n_s:]

    g_s = g1[:,:n_s]
    g_x = g1[:,n_s:n_s+n_x]
    g_e = g1[:,n_v:]

    A = np.row_stack([
        np.column_stack( [ np.eye(n_s), np.zeros((n_s,n_x)) ] ),
        np.column_stack( [ -f_snext    , -f_xnext             ] )
    ])
    B = np.row_stack([
        np.column_stack( [ g_s, g_x ] ),
        np.column_stack( [ f_s, f_x ] )
    ])

    [S,T,Q,Z,eigval] = qzordered(A,B,n_s)
    
    Z11 = Z[:n_s,:n_s]
    Z12 = Z[:n_s,n_s:]
    Z21 = Z[n_s:,:n_s]
    Z22 = Z[n_s:,n_s:]
    S11 = S[:n_s,:n_s]
    T11 = T[:n_s,:n_s]

    # first order solution
    C = solve(Z11.T, Z21.T).T
    P = np.dot(solve(S11.T, Z11.T).T , solve(Z11.T, T11.T).T )
    Q = g_e

    if False:
        from numpy import dot
        test = f_s + dot(f_x,C) + dot( f_snext, g_s + dot(g_x,C) ) + dot(f_xnext, dot( C, g_s + dot(g_x,C) ) )
        print('Error: ' + str(abs(test).max()))

    if approx_order == 1:
        return [C]

    # second order solution
    from dolo.numeric.tensor import sdot, mdot
    from numpy import dot
    from dolo.numeric.matrix_equations import solve_sylvester

    f2 = f_fun[2]
    g2 = g_fun[2]
    g_ss = g2[:,:n_s,:n_s]
    g_sx = g2[:,:n_s,n_s:n_v]
    g_xx = g2[:,n_s:n_v,n_s:n_v]

    X_s = C

    V1_3 = g_s + dot(g_x,X_s)
    V1 = np.row_stack([
        np.eye(n_s),
        X_s,
        V1_3,
        dot( X_s, V1_3 )
    ])

    K2 = g_ss + 2 * sdot(g_sx,X_s) + mdot(g_xx,[X_s,X_s])
    #L2 =
    A = f_x + dot( f_snext + dot(f_xnext,X_s), g_x)
    B = f_xnext
    C = V1_3
    D = mdot(f2,[V1,V1]) + sdot(f_snext + dot(f_xnext,X_s),K2)
    
    X_ss = solve_sylvester(A,B,C,D)

#    test = sdot( A, X_ss ) + sdot( B,  mdot(X_ss,[V1_3,V1_3]) ) + D

    
    if not sigma == None:
        g_ee = g2[:,n_v:,n_v:]

        v = np.row_stack([
            g_e,
            dot(X_s,g_e)
        ])

        K_tt = mdot( f2[:,n_v:,n_v:], [v,v] )
        K_tt += sdot( f_snext + dot(f_xnext,X_s) , g_ee )
        K_tt += mdot( sdot( f_xnext, X_ss), [g_e, g_e] )
        K_tt = np.tensordot( K_tt, sigma, axes=((1,2),(0,1)))

        if sigma2_correction is not None:
            K_tt += sdot( f_snext + dot(f_xnext,X_s) , sigma2_correction[0] )

        L_tt = f_x  + dot(f_snext, g_x) + dot(f_xnext, dot(X_s, g_x) + np.eye(n_x) )
        from numpy.linalg import det
        X_tt = solve( L_tt, - K_tt)

    if approx_order == 2:
        if sigma == None:
            return [X_s,X_ss]  # here, we don't approximate the law of motion of the states
        else:
            return [[X_s,X_ss],[X_tt]]  # here, we don't approximate the law of motion of the states

    # third order solution

    f3 = f_fun[3]
    g3 = g_fun[3]
    g_sss = g3[:,:n_s,:n_s,:n_s]
    g_ssx = g3[:,:n_s,:n_s,n_s:n_v]
    g_sxx = g3[:,:n_s,n_s:n_v,n_s:n_v]
    g_xxx = g3[:,n_s:n_v,n_s:n_v,n_s:n_v]

    V2_3 = K2 + sdot(g_x,X_ss)
    V2 = np.row_stack([
        np.zeros( (n_s,n_s,n_s) ),
        X_ss,
        V2_3,
        dot( X_s, V2_3 ) + mdot(X_ss,[V1_3,V1_3])
    ])

    K3 = g_sss + 3*sdot(g_ssx,X_s) + 3*mdot(g_sxx,[X_s,X_s]) + 2*sdot(g_sx,X_ss)
    K3 += 3*mdot( g_xx,[X_ss,X_s] ) + mdot(g_xxx,[X_s,X_s,X_s])
    L3 = 3*mdot(X_ss,[V1_3,V2_3])

    # A = f_x + dot( f_snext + dot(f_xnext,X_s), g_x) # same as before
    # B = f_xnext # same
    # C = V1_3 # same
    D = mdot(f3,[V1,V1,V1]) + 3*mdot(f2,[ V2,V1 ]) + sdot(f_snext + dot(f_xnext,X_s),K3)
    D += sdot( f_xnext, L3 )

    X_sss = solve_sylvester(A,B,C,D)

    # now doing sigma correction with sigma replaced by l in the subscripts

    if not sigma is None:
        g_se= g2[:,:n_s,n_v:]
        g_xe= g2[:,n_s:n_v,n_v:]

        g_see= g3[:,:n_s,n_v:,n_v:]
        g_xee= g3[:,n_s:n_v,n_v:,n_v:]


        W_l = np.row_stack([
            g_e,
            dot(X_s,g_e)
        ])

        I_e = np.eye(n_e)

        V_sl = g_se + mdot( g_xe, [X_s, np.eye(n_e)])

        W_sl = np.row_stack([
            V_sl,
            mdot( X_ss, [ V1_3, g_e ] ) + sdot( X_s, V_sl)
        ])

        K_ee = mdot(f3[:,:,n_v:,n_v:], [V1, W_l, W_l ])
        K_ee += 2 * mdot( f2[:,n_v:,n_v:], [W_sl, W_l])

        # stochastic part of W_ll

        SW_ll = np.row_stack([
            g_ee,
            mdot(X_ss, [g_e, g_e]) + sdot(X_s, g_ee)
        ])

        DW_ll = np.concatenate([
            X_tt,
            dot(g_x, X_tt),
            dot(X_s, sdot(g_x,X_tt )) + X_tt
        ])

        K_ee += mdot( f2[:,:,n_v:], [V1, SW_ll])

        K_ = np.tensordot(K_ee, sigma, axes=((2,3),(0,1)))

        K_ += mdot(f2[:,:,n_s:], [V1, DW_ll])

        def E(vec):
            n = len(vec.shape)
            return np.tensordot(vec,sigma,axes=((n-2,n-1),(0,1)))

        L = sdot(g_sx,X_tt) + mdot(g_xx,[X_s,X_tt])

        L += E(g_see + mdot(g_xee,[X_s,I_e,I_e]) )

        M = E( mdot(X_sss,[V1_3, g_e, g_e]) + 2*mdot(X_ss, [V_sl,g_e]) )
        M += mdot( X_ss, [V1_3, E( g_ee ) + sdot(g_x, X_tt)] )


        A = f_x + dot( f_snext + dot(f_xnext,X_s), g_x) # same as before
        B = f_xnext # same
        C = V1_3 # same
        D = K_ + dot( f_snext + dot(f_xnext,X_s), L) + dot( f_xnext, M )

        if sigma2_correction is not None:
            g_sl = sigma2_correction[1][:,:n_s]
            g_xl = sigma2_correction[1][:,n_s:(n_s+n_x)]
            D += dot( f_snext + dot(f_xnext,X_s), g_sl + dot(g_xl,X_s) )   # constant

        X_stt = solve_sylvester(A,B,C,D)

    if approx_order == 3:
        if sigma is None:
            return [X_s,X_ss,X_sss]
        else:
            return [[X_s,X_ss,X_sss],[X_tt, X_stt]]
