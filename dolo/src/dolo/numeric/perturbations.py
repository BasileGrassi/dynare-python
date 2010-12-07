from dolo.compiler.compiler_python import PythonCompiler
from dolo.numeric.matrix_equations import second_order_solver, solve_sylvester
from dolo.numeric.tensor import sdot,mdot
from dolo.numeric.decision_rules import DynareDecisionRule as DDR


import numpy as np

TOL = 1E-10

def solve_decision_rule(model,order=2,method='default'):
    
    Sigma = np.array(model.covariances).astype(np.float64)

    [y,x,parms] = compute_steadystate_values(model)
    #pc = PythonCompiler(model)
    pc = model.compiler
    if method == 'default':
        p_dynamic = pc.compute_dynamic_pfile_cached(order,False,False)
    elif method in ('sigma2','full'):
        p_dynamic = pc.compute_dynamic_pfile_cached(order,False,True)
        #p_dynamic = pc.compute_dynamic_pfile_cached(order,True,False)
    else:
        raise Exception('Unknown method : ' + method)

    # Build the approximation point to take the derivatives
    yy = np.concatenate([y,y,y])
    xx = np.array(x)
    xx = np.atleast_2d(xx)
    parms = np.array(parms)

    derivatives = p_dynamic(yy,xx,parms)

    res = derivatives[0]
    if abs(res).max() > TOL:
        raise Exception("Initial values don't satisfy static equations")

    if (method == 'sigma2'):
        if order == 2:
            [f_0,f_1,f_2] = derivatives
        elif order == 3:
            [f_0,f_1,f_2,f_3] = derivatives
            
        n_s = len(model.shocks)
        n_v = len(model.variables)
        nt = n_v*3 +n_s
        nn = nt+1

        h_1 = f_1[:,:nn]
        h_2 = f_2[:,:nn,:nn] # derivatives with sigma

        ft_1 = f_1[:,:nt]
        ft_2 = f_2[:,:nt,:nt] # traditionnal derivatives

        f1_A = f_1[:,:n_v]
        f1_B = f_1[:,n_v:(2*n_v)]
        f1_C = f_1[:,(2*n_v):(3*n_v)]
        f1_D = f_1[:,(3*n_v):(3*n_v+n_s)]
        f1_E = f_1[:,(3*n_v+n_s):(3*n_v+n_s+1)]

        derivatives = [f_0,ft_1,ft_2]

        if order == 3:
            h_3 = f_3[:,:nn,:nn,:nn]
            ft_3 = f_3[:,:nt,:nt,:nt]
            derivatives.append(ft_3)

    if method in ('sigma2','default'):
        d = perturb_solver(derivatives, Sigma, max_order=order)
        
    elif method == 'full':
        n_s = len(model.shocks)
        n_v = len(model.variables)
        n_p = len(model.parameters)        
        resp = new_solver_with_p(derivatives,(n_v,n_s,n_p),max_order=order)
        return resp


    ddr = DDR( d , model )

    if method == 'sigma2':

        if order >= 2:

            g_a = d['g_a']
            g_e = d['g_e']
            g_aa = d['g_aa']
            g_ae = d['g_ae']
            g_ee = d['g_ee']
            I = np.eye(n_v,n_v)
            A_inv = np.linalg.inv( sdot(f1_A,g_a+I) + f1_B )
            V_s = np.zeros( (n_v*3+n_s+1,))
            V_s[-1] = 1
            K_ss = mdot(f_2[:,:n_v,:n_v],[g_e,g_e]) + sdot( f1_A, g_ee )
            rhs = np.tensordot( K_ss,Sigma) + mdot(h_2,[V_s,V_s])
            sigma2 = sdot(A_inv,-rhs) / 2
            ddr.sigma2 = sigma2

        return ddr
    
def compute_steadystate_values(model):
    from dolo.misc.calculus import solve_triangular_system

    dvars = dict()
    dvars.update(model.parameters_values)
    dvars.update(model.init_values)
    for v in model.variables:
        if v not in dvars:
            dvars[v] = 0
    undeclared_parameters = []
    for p in model.parameters:
        if p not in dvars:
            undeclared_parameters.append(p)
            dvars[p] = 0
            raise Warning('No initial value for parameters : ' + str.join(', ', [p.name for p in undeclared_parameters]) )

    values = solve_triangular_system(dvars)[0]

    y = [values[v] for v in model.variables]
    x = [0 for s in model.shocks]
    params = [values[v] for v in model.parameters]
    return [y,x,params]


def perturb_solver(derivatives, Sigma, max_order=2):

    if max_order == 1:
        [f_0,f_1] = derivatives
    elif max_order == 2:
        [f_0,f_1,f_2] = derivatives
    elif max_order == 3:
        [f_0,f_1,f_2,f_3] = derivatives
    else:
        raise Exception('Perturbations not implemented at order {0}'.format(max_order))
    derivs = derivatives

    f = derivs
    n = f[0].shape[0] # number of variables
    s = f[1].shape[1] - 3*n
    [n_v,n_s] = [n,s]


    f1_A = f[1][:,:n]
    f1_B = f[1][:,n:(2*n)]
    f1_C = f[1][:,(2*n):(3*n)]
    f1_D = f[1][:,(3*n):]


    ## first order
    [ev,g_x] = second_order_solver(f1_A,f1_B,f1_C)

    res = np.dot(f1_A,np.dot(g_x,g_x)) + np.dot(f1_B,g_x) + f1_C

    mm = np.dot(f1_A, g_x) + f1_B

    g_u = - np.linalg.solve( mm , f1_D )

    if max_order == 1:
        d = {'ev':ev, 'g_a': g_x, 'g_e': g_u}
        return d

    # we need it for higher order
    V_a = np.concatenate( [np.dot(g_x,g_x),g_x,np.eye(n_v),np.zeros((s,n))] )
    V_e = np.concatenate( [np.dot(g_x,g_u),g_u,np.zeros((n_v,n_s)),np.eye(n_s)] )

    # Translation

    f_1 = f[1]
    f_2 = f[2]
    f_d = f1_A
    f_a = f1_B
    g_a = g_x
    g_e = g_u
    n_a = n_v
    n_e = n_s

    # Once for all !
    A = f_a + sdot(f_d,g_a)
    B = f_d
    C = g_a
    A_inv = np.linalg.inv(A)


    ##################
    # Automatic code #
    ##################

    #----------Computing order 2

    order = 2

    #--- Computing derivatives ('a', 'a')

    K_aa =  + mdot(f_2,[V_a,V_a])
    L_aa = np.zeros( (n_v, n_v, n_v) )

    #We need to solve the infamous sylvester equation
    #A = f_a + sdot(f_d,g_a)
    #B = f_d
    #C = g_a
    D = K_aa + sdot(f_d,L_aa)
    g_aa = solve_sylvester(A,B,C,D)

    if order < max_order:
        Y = L_aa + mdot(g_a,[g_aa]) + mdot(g_aa,[g_a,g_a])
        assert( abs(mdot(g_a,[g_aa]) - sdot(g_a,g_aa)).max() == 0)
        Z = g_aa
        V_aa = build_V(Y,Z,(n_a,n_e))

    #--- Computing derivatives ('a', 'e')

    K_ae =  + mdot(f_2,[V_a,V_e])
    L_ae =  + mdot(g_aa,[g_a,g_e])

    #We solve A*X + const = 0
    const = sdot(f_d,L_ae) + K_ae
    g_ae = - sdot(A_inv, const)

    if order < max_order:
        Y = L_ae + mdot(g_a,[g_ae])
        Z = g_ae
        V_ae = build_V(Y,Z,(n_a,n_e))

    #--- Computing derivatives ('e', 'e')

    K_ee =  + mdot(f_2,[V_e,V_e])
    L_ee =  + mdot(g_aa,[g_e,g_e])

    #We solve A*X + const = 0
    const = sdot(f_d,L_ee) + K_ee
    g_ee = - sdot(A_inv, const)

    if order < max_order:
        Y = L_ee + mdot(g_a,[g_ee])
        Z = g_ee
        V_ee = build_V(Y,Z,(n_a,n_e))

    # manual
    I = np.eye(n_v,n_v)
    M_inv = np.linalg.inv( sdot(f1_A,g_a+I) + f1_B )
    K_ss = mdot(f_2[:,:n_v,:n_v],[g_e,g_e]) + sdot( f1_A, g_ee )
    rhs =  - np.tensordot( K_ss, Sigma, axes=((1,2),(0,1)) ) #- mdot(h_2,[V_s,V_s])
    g_ss = sdot(M_inv,rhs)
    ghs2 = g_ss/2

    if max_order == 2:
        d = {
            'ev': ev,
            'g_a': g_a,
            'g_e': g_e,
            'g_aa': g_aa,
            'g_ae': g_ae,
            'g_ee': g_ee,
            'g_ss': g_ss
        }
        return d
    # /manual

    #----------Computing order 3

    order = 3

    #--- Computing derivatives ('a', 'a', 'a')

    K_aaa =  + 3*mdot(f_2,[V_a,V_aa]) + mdot(f_3,[V_a,V_a,V_a])
    L_aaa =  + 3*mdot(g_aa,[g_a,g_aa])
    
    #K_aaa =  2*( mdot(f_2,[V_aa,V_a]) ) + mdot(f_2,[V_a,V_aa]) + mdot(f_3,[V_a,V_a,V_a])
    #L_aaa =  2*( mdot(g_aa,[g_aa,g_a]) ) + mdot(g_aa,[g_a,g_aa])
    #K_aaa =  ( mdot(f_2,[V_aa,V_a]) + mdot(f_2,[V_a,V_aa]) )*3.0/2.0 + mdot(f_3,[V_a,V_a,V_a])
    #L_aaa =  ( mdot(g_aa,[g_aa,g_a]) + mdot(g_aa,[g_a,g_aa]) )*3.0/2.0


    #K_aaa = (K_aaa + K_aaa.swapaxes(3,2) + K_aaa.swapaxes(1,2) + K_aaa.swapaxes(1,2).swapaxes(2,3) + K_aaa.swapaxes(1,3) + K_aaa.swapaxes(1,3).swapaxes(2,3) )/6
    #L_aaa = (L_aaa + L_aaa.swapaxes(3,2) + L_aaa.swapaxes(1,2) + L_aaa.swapaxes(1,2).swapaxes(2,3) + L_aaa.swapaxes(1,3) + L_aaa.swapaxes(1,3).swapaxes(2,3) )/6

    
    #We need to solve the infamous sylvester equation
    #A = f_a + sdot(f_d,g_a)
    #B = f_d
    #C = g_a
    D = K_aaa + sdot(f_d,L_aaa)
    g_aaa = solve_sylvester(A,B,C,D)

    if order < max_order:
        Y = L_aaa + mdot(g_a,[g_aaa]) + mdot(g_aaa,[g_a,g_a,g_a])
        Z = g_aaa
        V_aaa = build_V(Y,Z,(n_a,n_e))

    # we transform g_aaa into a symmetric multilinear form
    g_aaa = (g_aaa + g_aaa.swapaxes(3,2) + g_aaa.swapaxes(1,2) + g_aaa.swapaxes(1,2).swapaxes(2,3) + g_aaa.swapaxes(1,3) + g_aaa.swapaxes(1,3).swapaxes(2,3) )/6

    #--- Computing derivatives ('a', 'a', 'e')

    K_aae =  + mdot(f_2,[V_aa,V_e]) + 2*mdot(f_2,[V_a,V_ae]) + mdot(f_3,[V_a,V_a,V_e])
    L_aae =  + mdot(g_aa,[g_aa,g_e]) + 2*mdot(g_aa,[g_a,g_ae]) + mdot(g_aaa,[g_a,g_a,g_e])

    #We solve A*X + const = 0
    const = sdot(f_d,L_aae) + K_aae
    g_aae = - sdot(A_inv, const)

    if order < max_order:
        Y = L_aae + mdot(g_a,[g_aae])
        Z = g_aae
        V_aae = build_V(Y,Z,(n_a,n_e))

    #--- Computing derivatives ('a', 'e', 'e')

    K_aee =  + 2*mdot(f_2,[V_ae,V_e]) + mdot(f_2,[V_a,V_ee]) + mdot(f_3,[V_a,V_e,V_e])
    L_aee =  + 2*mdot(g_aa,[g_ae,g_e]) + mdot(g_aa,[g_a,g_ee]) + mdot(g_aaa,[g_a,g_e,g_e])

    #We solve A*X + const = 0
    const = sdot(f_d,L_aee) + K_aee
    g_aee = - sdot(A_inv, const)

    if order < max_order:
        Y = L_aee + mdot(g_a,[g_aee])
        Z = g_aee
        V_aee = build_V(Y,Z,(n_a,n_e))

    #--- Computing derivatives ('e', 'e', 'e')

    K_eee =  + 3*mdot(f_2,[V_e,V_ee]) + mdot(f_3,[V_e,V_e,V_e])
    L_eee =  + 3*mdot(g_aa,[g_e,g_ee]) + mdot(g_aaa,[g_e,g_e,g_e])

    #We solve A*X + const = 0
    const = sdot(f_d,L_eee) + K_eee
    g_eee = - sdot(A_inv, const)

    if order < max_order:
        Y = L_eee + mdot(g_a,[g_eee])
        Z = g_eee
        V_eee = build_V(Y,Z,(n_a,n_e))


    ####################################
    ## Compute sigma^2 correction term #
    ####################################

    # ( a s s )

    A = f_a + sdot(f_d,g_a)    
    I_e = np.eye(n_e)

    Y = g_e
    Z = np.zeros((n_a,n_e))
    V_s = build_V(Y,Z,(n_a,n_e))

    Y = mdot( g_ae, [g_a, I_e] )
    Z = np.zeros((n_a,n_a,n_e))
    V_as = build_V(Y,Z,(n_a,n_e))

    Y = sdot(g_a,g_ss) + g_ss + np.tensordot(g_ee,Sigma)
    Z = g_ss
    V_ss = build_V(Y,Z,(n_a,n_e))

    K_ass_1 =  2*mdot(f_2,[V_as,V_s] ) + mdot(f_3,[V_a,V_s,V_s])
    K_ass_1 = np.tensordot(K_ass_1,Sigma)

    K_ass_2 = mdot( f_2, [V_a,V_ss] )

    K_ass = K_ass_1 + K_ass_2

    L_ass = mdot( g_aa, [g_a, g_ss]) + np.tensordot( mdot(g_aee,[g_a, I_e, I_e]), Sigma)

    D = K_ass + sdot(f_d,L_ass)

    g_ass = solve_sylvester( A, B, C, D)


    # ( e s s )

    A = f_a + sdot(f_d,g_a)
    A_inv = np.linalg.inv(A)
    I_e = np.eye(n_e)

    Y = g_e
    Z = np.zeros((n_a,n_e))
    V_s = build_V(Y,Z,(n_a,n_e))

    Y = mdot( g_ae, [g_e, I_e] )
    Z = np.zeros((n_a,n_e,n_e))
    V_es = build_V(Y,Z,(n_a,n_e))

    Y = sdot(g_a,g_ss) + g_ss + np.tensordot(g_ee,Sigma)
    Z = g_ss
    V_ss = build_V(Y,Z,(n_a,n_e))

    K_ess_1 =  2*mdot(f_2,[V_es,V_s] ) + mdot(f_3,[V_e,V_s,V_s])
    K_ess_1 = np.tensordot(K_ess_1,Sigma)

    K_ess_2 = mdot( f_2, [V_e,V_ss] )

    K_ess = K_ess_1 + K_ess_2

    L_ess = mdot( g_aa, [g_e, g_ss]) + np.tensordot( mdot(g_aee,[g_e, I_e, I_e]), Sigma)
    L_ess += mdot( g_ass, [g_e])

    D = K_ess + sdot(f_d,L_ess)

    g_ess = sdot( A_inv, -D)



    if max_order == 3:
        d = {'ev':ev,'g_a':g_a,'g_e':g_e, 'g_aa':g_aa, 'g_ae':g_ae, 'g_ee':g_ee,
    'g_aaa':g_aaa, 'g_aae':g_aae, 'g_aee':g_aee, 'g_eee':g_eee, 'g_ss':g_ss, 'g_ass':g_ass,'g_ess':g_ess}
        return  d


        
def new_solver_with_p(derivatives, sizes, max_order=2):
    
    if max_order == 1:
        [f_0,f_1] = derivatives
    elif max_order == 2:
        [f_0,f_1,f_2] = derivatives
    elif max_order == 3:
        [f_0,f_1,f_2,f_3] = derivatives
    derivs = derivatives
    
    f = derivs
    #n = f[0].shape[0] # number of variables
    #s = f[1].shape[1] - 3*n
    [n_v,n_s,n_p] = sizes

    n = n_v
    
    f1_A = f[1][:,:n]
    f1_B = f[1][:,n:(2*n)]
    f1_C = f[1][:,(2*n):(3*n)]
    f1_D = f[1][:,(3*n):((3*n)+n_s)]
    f1_E = f[1][:,((3*n)+n_s):]

    ## first order
    [ev,g_x] = second_order_solver(f1_A,f1_B,f1_C)
    
    mm = np.dot(f1_A, g_x) + f1_B
    
    g_u = - np.linalg.solve( mm , f1_D )
    g_p = - np.linalg.solve( mm , f1_E )

    if max_order == 1:
        return [g_x,g_u,g_p]
    
    # we need it for higher order

    V_x = np.concatenate( [np.dot(g_x,g_x),g_x,np.eye(n_v),np.zeros((n_s,n_v)), np.zeros((n_p,n_v))] )
    V_u = np.concatenate( [np.dot(g_x,g_u),g_u,np.zeros((n_v,n_s)),np.eye(n_s), np.zeros((n_p,n_s))] )
    V_p = np.concatenate( [np.dot(g_x,g_p),g_p,np.zeros((n_v,n_p)),np.zeros((n_s,n_p)), np.eye(n_p)] )
    V = [None, [V_x,V_u]]
    
    # Translation    
    n_a = n_v
    n_e = n_s
    n_p = g_p.shape[1]
    
    f_1 = f[1]
    f_2 = f[2]
    f_d = f1_A
    f_a = f1_B
    f_h = f1_C
    f_u = f1_D
    V_a = V_x
    V_e = V_u
    g_a = g_x
    g_e = g_u

    # Once for all !    
    A = f_a + sdot(f_d,g_a)
    B = f_d
    C = g_a    
    A_inv = np.linalg.inv(A)
        
    #----------Computing order 2
    
    order = 2
    
    #--- Computing derivatives ('a', 'a')
    
    K_aa =  + mdot(f_2,[V_a,V_a])
    L_aa = np.zeros((n_v, n_a, n_a))
    
    #We need to solve the infamous sylvester equation
    #A = f_a + sdot(f_d,g_a)
    #B = f_d
    #C = g_a
    D =  K_aa + sdot(f_d,L_aa)
    g_aa = solve_sylvester(A,B,C,D)
    
    if order < max_order:
        Y = L_aa + mdot(g_a,[g_aa]) + mdot(g_aa,[g_a,g_a])
        Z = g_aa
        V_aa = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'e')
    
    K_ae =  + mdot(f_2,[V_a,V_e])
    L_ae =  + mdot(g_aa,[g_a,g_e])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_ae) + K_ae
    g_ae = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_ae + mdot(g_a,[g_ae])
        Z = g_ae
        V_ae = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'p')
    
    K_ap =  + mdot(f_2,[V_a,V_p])
    L_ap =  + mdot(g_aa,[g_a,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_ap) + K_ap
    g_ap = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_ap + mdot(g_a,[g_ap])
        Z = g_ap
        V_ap = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('e', 'e')
    
    K_ee =  + mdot(f_2,[V_e,V_e])
    L_ee =  + mdot(g_aa,[g_e,g_e])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_ee) + K_ee
    g_ee = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_ee + mdot(g_a,[g_ee])
        Z = g_ee
        V_ee = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('e', 'p')
    
    K_ep =  + mdot(f_2,[V_e,V_p])
    L_ep =  + mdot(g_aa,[g_e,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_ep) + K_ep
    g_ep = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_ep + mdot(g_a,[g_ep])
        Z = g_ep
        V_ep = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('p', 'p')
    
    K_pp =  + mdot(f_2,[V_p,V_p])
    L_pp =  + mdot(g_aa,[g_p,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_pp) + K_pp
    g_pp = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_pp + mdot(g_a,[g_pp])
        Z = g_pp
        V_pp = build_V(Y,Z,(n_a,n_e,n_p))
        
    if max_order == 2:
        der_p = [g_p, [g_ap,g_ep], g_pp]
        return [[g_a,g_e], [g_aa,g_ae,g_ee],der_p]
    
    #----------Computing order 3
    
    order = 3
    
    #--- Computing derivatives ('a', 'a', 'a')
    
    K_aaa =  + 3*mdot(f_2,[V_a,V_aa]) + mdot(f_3,[V_a,V_a,V_a])
    L_aaa =  + 3*mdot(g_aa,[g_a,g_aa])
    
    #We need to solve the infamous sylvester equation
    #A = f_a + sdot(f_d,g_a)
    #B = f_d
    #C = g_a
    D = K_aaa + sdot(f_d,L_aaa)
    g_aaa = solve_sylvester(A,B,C,D)
    
    if order < max_order:
        Y = L_aaa + mdot(g_a,[g_aaa]) + mdot(g_aaa,[g_a,g_a,g_a])
        Z = g_aaa
        V_aaa = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'a', 'e')
    
    K_aae =  + mdot(f_2,[V_aa,V_e]) + 2*mdot(f_2,[V_a,V_ae]) + mdot(f_3,[V_a,V_a,V_e])
    L_aae =  + mdot(g_aa,[g_aa,g_e]) + 2*mdot(g_aa,[g_a,g_ae]) + mdot(g_aaa,[g_a,g_a,g_e])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_aae) + K_aae
    g_aae = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_aae + mdot(g_a,[g_aae])
        Z = g_aae
        V_aae = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'a', 'p')
    
    K_aap =  + mdot(f_2,[V_aa,V_p]) + 2*mdot(f_2,[V_a,V_ap]) + mdot(f_3,[V_a,V_a,V_p])
    L_aap =  + mdot(g_aa,[g_aa,g_p]) + 2*mdot(g_aa,[g_a,g_ap]) + mdot(g_aaa,[g_a,g_a,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_aap) + K_aap
    g_aap = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_aap + mdot(g_a,[g_aap])
        Z = g_aap
        V_aap = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'e', 'e')
    
    K_aee =  + 2*mdot(f_2,[V_ae,V_e]) + mdot(f_2,[V_a,V_ee]) + mdot(f_3,[V_a,V_e,V_e])
    L_aee =  + 2*mdot(g_aa,[g_ae,g_e]) + mdot(g_aa,[g_a,g_ee]) + mdot(g_aaa,[g_a,g_e,g_e])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_aee) + K_aee
    g_aee = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_aee + mdot(g_a,[g_aee])
        Z = g_aee
        V_aee = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'e', 'p')
    ll = [ mdot(f_2,[V_ae,V_p]) , mdot(f_2,[V_ap,V_e]), mdot(f_2,[V_a,V_ep]) , mdot(f_3,[V_a,V_e,V_p])     ]
    l = [ mdot(f_2,[V_ae,V_p]) , mdot(f_2,[V_ap,V_e]).swapaxes(2,3) , mdot(f_2,[V_a,V_ep]) , mdot(f_3,[V_a,V_e,V_p])     ]
    
    K_aep =  + mdot(f_2,[V_ae,V_p]) + mdot(f_2,[V_ap,V_e]).swapaxes(2,3) + mdot(f_2,[V_a,V_ep]) + mdot(f_3,[V_a,V_e,V_p])
    L_aep =  + mdot(g_aa,[g_ae,g_p]) + mdot(g_aa,[g_ap,g_e]).swapaxes(2,3) + mdot(g_aa,[g_a,g_ep]) + mdot(g_aaa,[g_a,g_e,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_aep) + K_aep
    g_aep = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_aep + mdot(g_a,[g_aep])
        Z = g_aep
        V_aep = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('a', 'p', 'p')
    
    K_app =  + 2*mdot(f_2,[V_ap,V_p]) + mdot(f_2,[V_a,V_pp]) + mdot(f_3,[V_a,V_p,V_p])
    L_app =  + 2*mdot(g_aa,[g_ap,g_p]) + mdot(g_aa,[g_a,g_pp]) + mdot(g_aaa,[g_a,g_p,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_app) + K_app
    g_app = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_app + mdot(g_a,[g_app])
        Z = g_app
        V_app = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('e', 'e', 'e')
    
    K_eee =  + 3*mdot(f_2,[V_e,V_ee]) + mdot(f_3,[V_e,V_e,V_e])
    L_eee =  + 3*mdot(g_aa,[g_e,g_ee]) + mdot(g_aaa,[g_e,g_e,g_e])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_eee) + K_eee
    g_eee = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_eee + mdot(g_a,[g_eee])
        Z = g_eee
        V_eee = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('e', 'e', 'p')
    
    K_eep =  + mdot(f_2,[V_ee,V_p]) + 2*mdot(f_2,[V_e,V_ep]) + mdot(f_3,[V_e,V_e,V_p])
    L_eep =  + mdot(g_aa,[g_ee,g_p]) + 2*mdot(g_aa,[g_e,g_ep]) + mdot(g_aaa,[g_e,g_e,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_eep) + K_eep
    g_eep = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_eep + mdot(g_a,[g_eep])
        Z = g_eep
        V_eep = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('e', 'p', 'p')
    
    K_epp =  + 2*mdot(f_2,[V_ep,V_p]) + mdot(f_2,[V_e,V_pp]) + mdot(f_3,[V_e,V_p,V_p])
    L_epp =  + 2*mdot(g_aa,[g_ep,g_p]) + mdot(g_aa,[g_e,g_pp]) + mdot(g_aaa,[g_e,g_p,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_epp) + K_epp
    g_epp = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_epp + mdot(g_a,[g_epp])
        Z = g_epp
        V_epp = build_V(Y,Z,(n_a,n_e,n_p))
    
    #--- Computing derivatives ('p', 'p', 'p')
    
    K_ppp =  + 3*mdot(f_2,[V_p,V_pp]) + mdot(f_3,[V_p,V_p,V_p])
    L_ppp =  + 3*mdot(g_aa,[g_p,g_pp]) + mdot(g_aaa,[g_p,g_p,g_p])
    
    #We solve A*X + const = 0
    const = sdot(f_d,L_ppp) + K_ppp
    g_ppp = - sdot(A_inv, const)
    
    if order < max_order:
        Y = L_ppp + mdot(g_a,[g_ppp])
        Z = g_ppp
        V_ppp = build_V(Y,Z,(n_a,n_e,n_p))
        
    der_p = [g_p, [g_ap,g_ep], [g_aap,g_aep,g_eep], g_pp, [g_app,g_epp], g_ppp]

    return [ [g_a,g_e], [g_aa,g_ae,g_ee], [g_aaa,g_aae,g_aee,g_eee], der_p]
    
def build_V(X,Y,others):

    ddim = X.shape[1:]
    new_dims = [(s,) + ddim for s in others]
    l = [X,Y] + [np.zeros(d) for d in new_dims]
    return np.concatenate(l, axis=0)
