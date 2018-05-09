# #############################################################################
# stat.py
# =======
# Author : Sepand KASHANI [sep@zurich.ibm.com]
# Revision : 0.0
# Last updated : 2018-04-05 14:09:31 UTC
# #############################################################################

"""
Statistical functions not available in :py:mod:`scipy`.
"""

import numpy as np
import scipy.linalg as linalg
import scipy.stats as stats

import pypeline.util.argcheck as chk


@chk.check(dict(S=lambda _: chk.has_reals(_) or chk.has_complex(_),
                df=chk.is_integer,
                normalize=chk.is_boolean))
def wishrnd(S, df, normalize=True) -> np.ndarray:
    """
    Wishart estimate of ``S`` with ``df`` degrees of freedom.

    :param S: [:py:class:`~numpy.ndarray`] (p, p) hermitian matrix.
    :param df: [:py:class:`~numbers.Integral` > p] degrees-of-freedom.
    :param normalize: [:py:class:`bool`] normalize estimate by ``df``.
        (Default: :py:obj:`True`)
    :return: [:py:class:`~numpy.ndarray`] (p, p) Wishart estimate.

    .. testsetup::

       import numpy as np
       from pypeline.util.math.stat import wishrnd

       np.random.seed(0)

       def hermitian_array(N: int) -> np.ndarray:
           '''
           Construct a (N, N) Hermitian matrix.
           '''
           i, j = np.triu_indices(N)
           A = np.zeros((N, N), dtype=complex)
           A[i, j] = np.random.randn(len(i)) + 1j * np.random.randn(len(i))
           A += A.conj().T
           return A

    .. doctest::

       >>> A = hermitian_array(N=4)
       >>> print(np.around(A, 2))
       [[ 3.53+0.j    0.4 +1.45j  0.98+0.76j  2.24+0.12j]
        [ 0.4 -1.45j  3.74+0.j   -0.98+0.33j  0.95+1.49j]
        [ 0.98-0.76j -0.98-0.33j -0.3 +0.j   -0.1 +0.31j]
        [ 2.24-0.12j  0.95-1.49j -0.1 -0.31j  0.82+0.j  ]]

       >>> B = wishrnd(A, df=7)
       >>> print(np.around(B, 2))
       [[0.56+0.j   0.94+0.1j  0.42-0.05j 0.55-0.21j]
        [0.94-0.1j  6.18+0.j   0.54-0.32j 1.08+0.26j]
        [0.42+0.05j 0.54+0.32j 2.67+0.j   0.66-2.36j]
        [0.55+0.21j 1.08-0.26j 0.66+2.36j 2.96+0.j  ]]
    """
    S = np.array(S, copy=False)
    p = len(S)

    if not (chk.has_shape(S, (p, p)) and
            np.allclose(S, S.conj().T)):
        raise ValueError('Parameter[S] must be hermitian symmetric.')
    if not (df > p):
        raise ValueError(f'Parameter[df] must be greater than {p}.')

    # L can be computed with a Cholesky decomposition, but the function only
    # works for full-rank matrices. To overcome this limitation, the Bartlett
    # decomposition is implemented instead.
    Sq = linalg.sqrtm(S)
    _, R = linalg.qr(Sq)
    L = R.conj().T

    A = np.zeros((p, p))
    A[np.diag_indices(p)] = np.sqrt(stats.chi2.rvs(df=df - np.arange(p)))
    A[np.tril_indices(p, k=-1)] = stats.norm.rvs(size=p * (p - 1) // 2)

    W = L @ A
    X = W @ W.conj().T / (df if normalize else 1)
    return X
