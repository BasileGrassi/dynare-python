"""
This module contains classes representing decision rules
"""

from dolo.misc.decorators import memoized

import numpy as np

class TaylorExpansion(dict):

    @property
    @memoized
    def order(self):
        order = 0
        if self.get('g_a') != None:
            order = 1
        if self.get('g_aa') != None:
            order = 2
        if self.get('g_aaa') != None:
            order = 3
        return order



class DynareDecisionRule(TaylorExpansion):


    def __init__(self,d,model):
        super(DynareDecisionRule,self).__init__(d)
        self.model = model
        self.dr_var_order_i = [model.variables.index(v) for v in model.dr_var_order]
        self.dr_states_order = [v for v in model.dr_var_order if v in model.state_variables]
        self.dr_states_i = [model.variables.index(v) for v in self.dr_states_order]

    @property
    @memoized
    def ghx(self):
        ghx = self.get('g_a')
        ghx = ghx[self.dr_var_order_i,:]
        ghx = ghx[:,self.dr_states_i]
        return ghx

    @property
    @memoized
    def ghu(self):
        ghu = self.get('g_e')
        ghu = ghu[self.dr_var_order_i,:]
        return ghu

    @property
    @memoized
    def ghxx(self):
        ghxx = self.get('g_aa')
        ghxx = ghxx[self.dr_var_order_i,:]
        ghxx = ghxx[:,self.dr_states_i,:]
        ghxx = ghxx[:,:,self.dr_states_i]
        n_v = ghxx.shape[0]
        n_s =  ghxx.shape[1]
        return ghxx.reshape( (n_v,n_s*n_s) )

    @property
    @memoized
    def ghxu(self):
        ghxu = self.get('g_ae')
        ghxu = ghxu[self.dr_var_order_i,:,:]
        ghxu = ghxu[:,self.dr_states_i,:]
        n_v = ghxu.shape[0]
        n_s = ghxu.shape[1]
        n_e = ghxu.shape[2]
        return ghxu.reshape( (n_v,n_s*n_e ))

    @property
    @memoized
    def ghuu(self):
        ghuu = self.get('g_ee')
        ghuu = ghuu[self.dr_var_order_i,:]
        n_v = ghuu.shape[0]
        n_e = ghuu.shape[1]
        return ghuu.reshape( (n_v,n_e*n_e) )

    @property
    @memoized
    def ghs2(self):
        return self.get('g_ss')


    @property
    @memoized
    def g_1(self):
        
        g_1x = self.ghx
        g_1u = self.ghu

        if 'g_ass' in self:
            correc_x_ss =  self['g_ass'][self.dr_var_order_i,:][:,self.dr_states_i]/2
            correc_u_ss =  self['g_ess'][self.dr_var_order_i,:]/2
            g_1x += correc_x_ss
            g_1u += correc_u_ss

        return np.column_stack([g_1x,g_1u])

    @property
    @memoized
    def g_2(self):
        n_v = self['g_a'].shape[0]
        n_s = len(self.dr_states_order)
        n_e = self['g_e'].shape[1]
        g_2 = np.zeros( (n_v,n_s+n_e,n_s+n_e) )


        g_2[:,n_s:,n_s:] = self.ghuu.reshape((n_v,n_e,n_e))
        g_2[:,:n_s,n_s:] = self.ghxu.reshape((n_v,n_s,n_e))
        g_2[:,n_s:,:n_s] = self.ghxu.reshape((n_v,n_s,n_e)).swapaxes(1,2)
        g_2[:,:n_s,:n_s] = self.ghxx.reshape((n_v,n_s,n_s))
        return fold( g_2 ) / 2

    @property
    @memoized
    def ghxxx(self):
        ghxxx = self['g_aaa'][self.dr_var_order_i,...]
        ghxxx = ghxxx[:,self.dr_states_i,:,:]
        ghxxx = ghxxx[:,:,self.dr_states_i,:]
        ghxxx = ghxxx[:,:,:,self.dr_states_i]
        return ghxxx

    @property
    @memoized
    def ghxxu(self):
        ghxxu = self['g_aae'][self.dr_var_order_i,...]
        ghxxu = ghxxu[:,self.dr_states_i,:,:]
        ghxxu = ghxxu[:,:,self.dr_states_i,:]
        return ghxxu

    @property
    @memoized
    def ghxuu(self):
        ghxuu = self['g_aee'][self.dr_var_order_i,...]
        ghxuu = ghxuu[:,self.dr_states_i,:,:]
        return ghxuu

    @property
    @memoized
    def ghuuu(self):
        ghuuu = self['g_eee'][self.dr_var_order_i,...]
        return ghuuu

    @property
    @memoized
    def g_3(self):
        n_v = self['g_a'].shape[0]
        n_s = len(self.dr_states_order)
        n_e = self['g_e'].shape[1]

        ghxxx = self.ghxxx
        ghxxu = self.ghxxu
        ghxuu = self.ghxuu
        ghuuu = self.ghuuu
        
        g_3 = np.zeros( (n_v,n_s+n_e,n_s+n_e,n_s+n_e))

        g_3[:,:n_s,:n_s,:n_s] = ghxxx

        g_3[:,:n_s,:n_s,n_s:] = ghxxu
        g_3[:,:n_s,n_s:,:n_s] = ghxxu.swapaxes(2,3)
        g_3[:,n_s:,:n_s,:n_s] = ghxxu.swapaxes(1,3)

        g_3[:, :n_s, n_s:, n_s:] = ghxuu
        g_3[:, n_s:, :n_s, n_s:] = ghxuu.swapaxes(1,2)
        g_3[:, n_s:, n_s:, :n_s] = ghxuu.swapaxes(1,3)

        g_3[:,n_s:,n_s:,n_s:] = ghuuu

        g_3 = symmetrize(g_3)

        return fold( g_3 ) / 2 / 3

    def __str__(self):
        txt = '''
Decision rule (order {order}) :
{msg}
    - States : {states}
    
    - Endogenous variables : {endo}

    - First order coefficients :

{foc}
'''
        import scipy
        mat = np.concatenate([self.ghx,self.ghu],axis=1)
        if self.order > 1:
            msg = '\n    (Only first order derivatives are printed)\n'
        else:
            msg = ''
        col_names = [str(v(-1)) for v in self.model.dr_var_order if v in self.model.state_variables] + [str(s) for s in self.model.shocks]
        row_names = [str(v) for v in self.model.dr_var_order]
        txt = txt.format(
            msg = msg,
            order=self.order,
            states=str.join(' ', col_names),
            endo=str.join(' ', row_names),
            foc=mat
        )
        return txt

        
        return txt

DecisionRule = DynareDecisionRule

def symmetrize(tens):
    return (tens + tens.swapaxes(3,2) + tens.swapaxes(1,2) + tens.swapaxes(1,2).swapaxes(2,3) + tens.swapaxes(1,3) + tens.swapaxes(1,3).swapaxes(2,3) )/6

def fold(tens):
    from itertools import product

    if tens.ndim == 3:
        n = tens.shape[0]
        q = tens.shape[1]
        assert( tens.shape[2] == q )

        non_decreasing_pairs = [ (i,j) for (i,j) in product(range(q),range(q)) if i<=j ]
        result = np.zeros( (n,len(non_decreasing_pairs) ) )
        for k,(i,j) in enumerate(non_decreasing_pairs):
            result[:,k] = tens[:,i,j]
        return result

    elif tens.ndim == 4:
        n = tens.shape[0]
        q = tens.shape[1]
        assert( tens.shape[2] == q )
        assert( tens.shape[3] == q)

        non_decreasing_tuples = [ (i,j,k) for (i,j,k) in product(range(q),range(q),range(q)) if i<=j<=k ]
        result = np.zeros( (n,len(non_decreasing_tuples) ) )
        for l,(i,j,k) in enumerate(non_decreasing_tuples):
            result[:,l] = tens[:,i,j,k]
        return result



def impulse_response_function(decision_rule, shock, variables = None, horizon=40, order=1, percentages=False, plot=True):
    
    if order > 1:
        raise Exception('irfs, for order > 1 not implemented')
    
    dr = decision_rule
    A = dr['g_a']
    B = dr['g_e']

    [n_v, n_s] = [ len(dr.model.variables), len(dr.model.shocks) ]


    if isinstance(shock,int):
        i_s = shock
    elif isinstance(shock,str):
        from dolo.symbolic.symbolic import Shock
        shock =  Shock(shock,0)
        i_s = dr.model.shocks.index( shock )
    else:
        i_s = shock

    E = np.zeros(  n_s )
    E[i_s] = 0.01

    simul = np.zeros( (n_v, horizon+1) )
    simul[:,0] = np.dot(B,E)
    for i in range(horizon):
        simul[:,i+1] = np.dot( A, simul[:,i])


    if percentages:
        for i in range(n_v):
            simul[i,:] = simul[i,:]/dr['ys'][i] * 100
    else:
        for i in range(n_v):
            simul[i,:] += dr['ys'][i]

    if variables:
        from dolo.symbolic.symbolic import Variable
        if not isinstance(variables,list):
            variables = [variables]
        variables =  [Variable(str(v),0) for v in variables]
        ind_vars = [dr.model.variables.index( v ) for v in variables]
        simul = simul[ind_vars, :]

    x = np.linspace(0,horizon,horizon+1)

    if plot:
        from matplotlib import pylab
        pylab.clf()
        pylab.title('Impulse-Response Function for ${var}$'.format(var=shock.__latex__()))
        for k in range(len(variables)):
            pylab.plot(x, simul[k,:],label='$'+variables[k]._latex_()+'$' )
        pylab.plot(x,x*0,'--',color='black')
        pylab.xlabel('$t$')
        if percentages:
            pylab.ylabel('% deviations from the steady-state')
        else:
            pylab.ylabel('Deviations from the steady-state')
        pylab.legend()
        filename = 'irf_' + str(shock) + '__' + '_' + str.join('_',[str(v) for v in variables])
        pylab.savefig(filename) # not good...
        #pylab.show()

    return simul

def stoch_simul(decision_rule, variables = None,  horizon=40, order=1, percentages=False, plot=True, seed=None):

    if order > 1:
        raise Exception('irfs, for order > 1 not implemented')

    dr = decision_rule
    A = dr['g_a']
    B = dr['g_e']

    [n_v, n_s] = [ len(dr.model.variables), len(dr.model.shocks) ]


#    if isinstance(shock,int):
#        i_s = shock
#    elif isinstance(shock,str):
#        from dolo.symbolic.symbolic import Shock
#        shock =  Shock(shock,0)
#        i_s = dr.model.shocks.index( shock )
#    else:
#        i_s = shock
#
#
#

    simul = np.zeros( (n_v, horizon+1) )


    Sigma = dr['Sigma']
    if seed:
        np.random.seed(seed)
    E = np.random.multivariate_normal((0,)*n_s,Sigma,horizon)
    E = E.T
    for i in range(horizon):
        simul[:,i+1] = np.dot( A, simul[:,i]) + np.dot( B, E[:,i] )


    if percentages:
        for i in range(n_v):
            simul[i,:] = simul[i,:]/dr['ys'][i] * 100
    else:
        for i in range(n_v):
            simul[i,:] += dr['ys'][i]

    if variables:
        from dolo.symbolic.symbolic import Variable
        if not isinstance(variables,list):
            variables = [variables]
        variables =  [Variable(str(v),0) for v in variables]
        ind_vars = [dr.model.variables.index( v ) for v in variables]
        simul = simul[ind_vars, :]

    x = np.linspace(0,horizon,horizon+1)

    if plot:
        from matplotlib import pylab
        pylab.clf()
        pylab.title('Stochastic simulation')
        for k in range(len(variables)):
            pylab.plot(x, simul[k,:],label='$'+variables[k]._latex_()+'$' )
        pylab.plot(x,x*0,'--',color='black')
        pylab.xlabel('$t$')
        if percentages:
            pylab.ylabel('% deviations from the steady-state')
        else:
            pylab.ylabel('Deviations from the steady-state')
        pylab.legend()
        filename = 'simul_' + '_' + str.join('_',[str(v) for v in variables])
        pylab.savefig(filename) # not good...
        #pylab.show()

    return simul