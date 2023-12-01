from typing import Optional
import numpy as np
import scipy as sp
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker


class TimeSeries:
    def __init__(self, time: np.ndarray, time_response: np.ndarray, label: list[str]):
        if time_response.ndim == 1:
            time_response = time_response.reshape(len(time_response), 1)
        if 'complex' in time_response.dtype.name:
            raise TypeError(time_response)
        self.time = time
        self.response = time_response
        self.label = label

    @property
    def dt(self) -> float:
        return self.time[1] - self.time[0]

    @property
    def tmax(self) -> float:
        return self.time[-1]

    def to_fft(self, sided: int=1, fft_type: str='real_imag'):
        tmax = self.tmax
        dts = np.diff(self.time)
        dt = dts.mean()
        ntimes = len(self.time)

        is_onesided_center = (ntimes % 2 == 1)
        frequency = _onesided_frequency(dt, tmax, ntimes)
        #df = 1 / tmax
        #fsampling = 1 / dt
        #fnyquist = fsampling / 2
        #frequency = np.arange(0, ntimes) * df

        response = _response_squeeze(self.response)
        fft_response = sp.fft.fft(response, n=None, axis=-1, norm=None,
                         overwrite_x=False, workers=None, plan=None)
        fft_response /= ntimes

        if fft_type == 'mag_phase':
            mag = np.abs(fft_response)
            phase = np.arctan2(fft_response.imag, fft_response.real)
            fft_response = mag + 1j * phase

        assert fft_response.shape[0] == ntimes, (fft_response.shape, ntimes)
        #assert sided == 1
        fft = FourierTransform(
            frequency, fft_response, label=self.label, fft_type=fft_type,
            sided=sided, is_onesided_center=is_onesided_center)
        return fft

    def to_psd_welch(self, sided: int=1, window: str='hann',
                     window_size_sec: float= 1.0,
                     overlap_sec: float=0.5):
        assert sided in {1, 2}, sided
        return_onesided = (sided == 1)
        #fsampling = 1 / self.dt

        #ntimes = len(self.time)
        #df = 1 / self.tmax
        fsampling = 1 / self.dt
        #fnyquist = fsampling / 2
        #frequency = np.arange(0, ntimes) * df

        window_size_int = int(fsampling * window_size_sec)
        overlap_int = int(fsampling * overlap_sec)

        #nfft - for 0 padded signals
        ntimes = len(self.time)
        #is_onesided_center = (ntimes % 2 == 1)
        response = _response_squeeze(self.response)
        frequency, psd_response = sp.signal.welch(
            response, fs=fsampling, window=window,
            nperseg=window_size_int, noverlap=overlap_int, nfft=None,
            detrend='constant', return_onesided=return_onesided,
            scaling='density', axis=-1, average='mean')

        fmax = frequency[-1]
        if sided == 1:
            is_onesided_center = not np.allclose(fmax, fsampling)
        else:
            # doesn't matter
            is_onesided_center = True
        psd = PowerSpectralDensity(
            frequency, psd_response, label=self.label,
            sided=sided, is_onesided_center=is_onesided_center,
            octave_spacing=0)
        return psd

    def to_psd(self, sided: int=1):
        assert sided in {1, 2}, sided
        tmax = self.time[-1]

        dt = self.dt
        #dts = np.diff(self.time)
        #dt = dts.mean()
        ntimes = len(self.time)

        frequency = _onesided_frequency(dt, tmax, ntimes)
        response = _response_squeeze(self.response)
        fft_response = sp.fft.fft(response, n=None, axis=-1, norm=None,
                                  overwrite_x=False, workers=None, plan=None)
        fft_response /= ntimes

        #psd_response = fft_response * np.conj(fft_response) / df
        psd_response = fft_to_psd_df(frequency, fft_response)
        assert fft_response.shape[0] == ntimes, (fft_response.shape, ntimes)
        is_onesided_center = (ntimes % 2 == 1)
        #assert sided == 1
        psd = PowerSpectralDensity(
            frequency, psd_response, label=self.label,
            sided=sided, is_onesided_center=is_onesided_center)
        return psd

    def plot(self, y_units: str='g', ifig: int=1, ax: Optional[plt.Axes]=None, linestyle='-o', show: bool=True):
        if ax is None:
            fig = plt.figure(ifig)
            ax = fig.gca()
        ax.set_title('Time Series')
        ax.set_xlabel('Time (sec)')
        ax.set_ylabel('Response (g)')
        ax.plot(self.time, self.response[:, 0], linestyle, label=self.label[0])
        ax.legend()
        ax.grid(True)
        if show:
            plt.show()

class FourierTransform:
    def __init__(self, frequency: np.ndarray, fft_response: np.ndarray, label: list[str],
                 fft_type: str='real_imag', sided: int=1, is_onesided_center: bool=None):
        if fft_response.ndim == 1:
            fft_response = fft_response.reshape(len(fft_response), 1)
        self.frequency = frequency
        self.response = fft_response
        self.label = label
        self.fft_type = fft_type
        self.sided = sided
        self.is_onesided_center = is_onesided_center
        assert is_onesided_center is not None
        assert fft_type in {'real_imag', 'mag_phase'}, fft_type

    @property
    def df(self) -> float:
        df = self.frequency[1] - self.frequency[0]
        return df
    @property
    def fsampling(self) -> float:
        fmax = self.frequency[-1]
        fsampling = _to_twosided_fsampling(fmax, self.df, self.sided, self.is_onesided_center)
        return fsampling

    def to_time(self):
        assert self.sided == 2, self.sided
        #fnyq = self.frequency[-1]
        #fsampling = fnyq * 2
        tmax = 1 / self.df
        dt = 1 / self.fsampling
        ntimes = np.ceil(tmax / dt)

        response = _response_squeeze(self.response) * ntimes
        ifft = sp.fft.ifft(response, n=None, axis=-1, norm=None,
                           overwrite_x=False, workers=None, plan=None)
        time = np.arange(0, ntimes) * dt
        time_series = TimeSeries(time, ifft.real, label=self.label)
        return time_series

    def to_psd(self, sided: int=1):
        psd_response = fft_to_psd_df(self.frequency, self.response)
        #toonesided
        psd = PowerSpectralDensity(
            self.frequency.copy(), psd_response, label=self.label,
            sided=sided, is_onesided_center=self.is_onesided_center)
        return psd

    def to_onesided(self, inplace: bool=True):
        if self.sided == 1:
            return self
        assert self.sided == 2, self.sided
        frequency, response, is_onesided_center = dft_to_onesided(self.frequency, self.response)

        self.sided = 1
        self.is_onesided_center = is_onesided_center
        return self

    def mag_phase(self) -> tuple[np.ndarray, np.ndarray]:
        response = self.response[:, 0]
        if self.fft_type == 'mag_phase':
            # e * (i theta) = cos(theta) + 1j*sin(theta)
            mag = response.real
            phase = response.imag
        else:
            mag = np.abs(response)
            phase = np.arctan2(response.imag, response.real)
        return mag, phase

    def real_imag(self) -> np.ndarray:
        response = self.response[:, 0]
        if self.fft_type == 'mag_phase':
            # e * (i theta) = cos(theta) + 1j*sin(theta)
            mag = response.real
            phase = response.imag
            real_imag = mag * (np.cos(phase) + 1j * np.sin(phase))
        else:
            real_imag = self.response
        return real_imag

    def plot_real_imag(self, ifig: int=1,
                       ax: Optional[tuple[plt.Axes, plt.Axes]]=None,
                       xscale: str='linear', show: bool=True):
        if ax is None:
            fig = plt.figure(ifig)
            ax1, ax2 = fig.subplots(nrows=2)
        else:
            ax1, ax2 = ax

        #ax.set_yscale(yscale)
        ax1.set_title('Fourier Transform - Real/Imag')
        ax1.set_xlabel('Frequency (Hz)')
        ax2.set_xlabel('Frequency (Hz)')

        ax1.set_ylabel('Real (g)')
        ax2.set_xlabel('Imag (g)')

        real_imag = self.real_imag()
        real = real_imag.real
        imag = real_imag.imag

        ax1.plot(self.frequency, real, '-o', label=self.label[0])
        ax2.plot(self.frequency, imag, '-o', label=self.label[0])
        ax2.legend()
        _adjust_axes_limit(ax2, imag)
        _set_grid(ax1, xscale, 'linear')
        _set_grid(ax2, xscale, 'linear')
        if show:
            plt.show()

    def plot_mag(self, ifig: int=1,
                 ax: Optional[plt.Axes]=None,
                 y_units: str='g',
                 xscale: str='linear',
                 yscale: str='linear',
                 linestyle: str='-o',
                 show: bool=True):
        if ax is None:
            fig = plt.figure(ifig)
            ax = fig.gca()
        #ax1.set_title('Fourier Transform - Mag')
        ax.set_xlabel('Frequency (Hz)')

        mag, phase = self.mag_phase()
        ax.plot(self.frequency, mag, linestyle, label=self.label[0])
        ax.legend()
        ax.set_ylabel(f'Magnitude ({y_units})')
        #ax.set_yticklabels(['{:,.0%}'.format(x) for x in current_values])
        _set_grid(ax, xscale, yscale)
        if show:
            plt.show()

    def plot_mag_phase(self, ifig: int=1,
                       ax: Optional[tuple[plt.Axes, plt.Axes]]=None,
                       xscale: str='linear', show: bool=True):
        if ax is None:
            fig = plt.figure(ifig)
            ax1, ax2 = fig.subplots(nrows=2)
        else:
            ax1, ax2 = ax
        ax1.set_title('Fourier Transform - Mag/Phase')
        ax1.set_xlabel('Frequency (Hz)')
        ax2.set_xlabel('Frequency (Hz)')

        mag, phase = self.mag_phase()
        ax1.plot(self.frequency, mag, '-o')
        ax2.plot(self.frequency, phase, '-o', label=self.label[0])
        ax2.legend()
        ax1.set_ylabel('Magnitude (g)')
        ax2.set_ylabel('Phase (rad)')
        _adjust_axes_limit(ax2, phase)

        _set_grid(ax1, xscale, 'linear') # yscale
        _set_grid(ax2, xscale, 'linear') # yscale
        if show:
            plt.show()

class PowerSpectralDensity:
    def __init__(self, frequency: np.ndarray, psd_response: np.ndarray, label: list[str],
                 sided: int=1, is_onesided_center: bool=None, octave_spacing: int=0):
        if psd_response.ndim == 1:
            psd_response = psd_response.reshape(len(psd_response), 1)
        if 'complex' in psd_response.dtype.name:
            raise TypeError(psd_response)
        assert psd_response.shape[1] == 1, psd_response.shape
        assert psd_response.ndim == 2, psd_response.shape
        self.frequency = frequency
        self.response = psd_response
        self.label = label
        self.octave_spacing = octave_spacing
        self.sided = sided
        self.is_onesided_center = is_onesided_center
        #assert sided == 2
        assert is_onesided_center is not None
        assert sided in {1, 2}, sided
        assert octave_spacing >= 0, octave_spacing
        assert isinstance(frequency, np.ndarray), type(frequency)
        assert isinstance(psd_response, np.ndarray), type(psd_response)
        #print('psd-init', self.fsampling, self.df, self.is_onesided_center)

    @property
    def df(self):
        if self.octave_spacing == 0:
            return self.frequency[1] - self.frequency[0]
        raise RuntimeError(self.octave_spacing)

    @property
    def fsampling(self) -> float:
        assert self.sided in {1, 2}
        if self.octave_spacing == 0:
            fmax = self.frequency[-1]
            df = self.df
            fsampling = _to_twosided_fsampling(
                fmax, df, sided=self.sided,
                is_onesided_center=self.is_onesided_center)
            return fsampling
        raise RuntimeError(self.octave_spacing)

    def to_time_series(self):
        if self.sided == 1:
            self = self.to_twosided(inplace=False)

        assert self.sided == 2, self.sided
        assert self.response.shape[1] == 1, self.response.shape
        if self.octave_spacing == 0:
            magnitude = np.sqrt(self.response * self.df)
            npoints = len(self.frequency)
            phase = np.random.uniform(-1., 1.) * np.pi
        else:
            raise NotImplementedError(self.octave_spacing)
        real_imag = magnitude * np.cos(phase) + 1j * np.sin(phase)
        real_imag *= npoints
        real_imag = _response_squeeze(real_imag)
        ifft = sp.fft.ifft(real_imag, n=None, axis=-1, norm=None,
                           overwrite_x=False, workers=None, plan=None)

        dt = 1 / self.fsampling
        time = np.arange(0, npoints) * dt
        time_series = TimeSeries(time, ifft.real, self.label)
        return time_series


    def to_miles_equation(self, Q: float):
        zeta = 1 / (2 * Q)
        vrs = np.sqrt(np.pi/(4*zeta) * np.frequency)
        return vrs

    def to_sdof_transmissibility(self, Q: float, fn: float):
        """https://www.dataphysics.com/blog/shock-analysis/understanding-shock-response-spectra/"""
        rho = self.frequency / fn
        rho2 = rho ** 2
        zeta = 1 / (2 * Q)
        num0 = 2j * zeta * rho
        num = 1 + num0
        denom = (1 - rho2) + num0
        transmissibility = num / denom
        trans = FourierTransform(
            self.frequency.copy(), transmissibility, self.label,
            sided=1, is_onesided_center=False,
            #octave_spacing=0,
        )
        return trans

    def to_sdof_vrs_response(self, Q: float, fn: float):
        """http://www.vibrationdata.com/tutorials_alt/frf.pdf"""
        zeta = 1 / (2 * Q)
        freq2 = self.frequency ** 2
        num = -fn ** 2 * freq2
        denom = fn ** 2 - freq2 + 1j * (2 * zeta * self.frequency * fn)

        psd_response = np.abs(num / denom)
        psd_response *= self.response[0, 0] / psd_response[0]
        vrs = VibrationResponseSpectra(
            self.frequency, psd_response.real, self.label,
            sided=1, is_onesided_center=False, octave_spacing=0)
        return vrs

    def to_vrs(self, Q: float):
        """vibration response spectra"""
        zeta = 1 / (2 * Q)
        df = np.diff(self.frequency).mean()
        if 0:
            rho = self.frequency[:, np.newaxis] / self.frequency[np.newaxis, :]
            rho2 = rho ** 2
            num0 = 4 * zeta ** 2 * rho2
            denom = ((1 - rho2) ** 2) + num0

            grms0 = ((1 + num0)/ denom)
            grms1 = grms0 * self.response[:, 0] * df
            grms = np.sqrt(grms1.sum(axis=0))
            assert len(grms) == len(self.frequency)
        elif 0:
            fn = 100.
            rho = self.frequency / fn
            rho2 = rho ** 2
            num0 = 4 * zeta ** 2 * rho2
            denom = ((1 - rho2) ** 2) + num0

            grms0 = (1 + num0)/ denom
            grms1 = grms0 * self.response[:, 0] * df
            grms = np.sqrt(grms1.sum())
            grmss = np.array([grms])
            freqs = np.array([fn])
        elif 1:
            freqs = self.frequency
            grmss = self.frequency.copy()
            for i, fn in enumerate(self.frequency):
                rho = self.frequency / fn
                rho2 = rho ** 2
                num0 = 4 * zeta ** 2 * rho2
                denom = ((1 - rho2) ** 2) + num0

                grms0 = (1 + num0)/ denom
                grms1 = grms0 * self.response[:, 0] * df
                grms = np.sqrt(grms1.sum())
                grmss[i] = grms

        vrs = VibrationResponseSpectra(
            freqs, grmss, label=self.label,
            sided=self.sided,
            is_onesided_center=self.is_onesided_center,
            octave_spacing=self.octave_spacing)
        return vrs

    def to_onesided(self, inplace: bool=True):
        if self.sided == 1:
            return self
        assert self.sided == 2, self.sided
        frequency, response, is_onesided_center = psd_to_onesided(
            self.frequency, self.response)
        if inplace:
            self.frequency = frequency
            self.response = response
            self.sided = 1
            self.is_onesided_center = is_onesided_center
            out = self
        else:
            out = PowerSpectralDensity(
                frequency.copy(), response.copy(), label=self.label, sided=1,
                is_onesided_center=is_onesided_center,
                octave_spacing=self.octave_spacing)
        return out

    def to_twosided(self, inplace: bool=True):
        if self.sided == 2:
            self.fsampling
            self.df
            return self
        assert self.sided == 1, self.sided

        #print('psd', self.fsampling, self.df, self.is_onesided_center)
        frequency, response = psd_to_twosided(self.frequency, self.response,
                                              self.is_onesided_center, self.df)
        if inplace:
            self.frequency = frequency
            self.response = response
            self.sided = 2
            out = self
        else:
            out = PowerSpectralDensity(
                frequency.copy(), response, self.label, sided=2,
                is_onesided_center=False,
                octave_spacing=self.octave_spacing)
        out.fsampling
        out.df
        return out

    def resample(self, frequency: np.ndarray, inplace: bool=True):
        """uses a log-log interp"""
        # TODO: get rid of for loop
        psd_response = np.zeros(self.response.shape, dtype=self.response.dtype)
        for iresp in range(self.response.shape[1]):
            responsei = self.response[:, iresp]
            psd_response = 2 ** np.interp(
                np.log2(frequency), np.log2(self.frequency), np.log2(responsei))

        if inplace:
            self.frequency = frequency
            self.response = psd_response
            out = self
        else:
            out = PowerSpectralDensity(
                frequency.copy(), psd_response, label=self.label,
                sided=self.sided, is_onesided_center=self.is_onesided_center,
                octave_spacing=self.octave_spacing)
        return out

    def plot(self, ifig: int=1,
             ax: Optional[plt.Axes]=None,
             y_units: str='g', xscale: str='log', yscale: str='log',
             xlim: Optional[tuple[float, float]]=None,
             ylim: Optional[tuple[float, float]]=None,
             linestyle='-o',
             show: bool=True):
        self.fsampling
        self.df
        if ax is None:
            fig = plt.figure(ifig)
            ax = fig.gca()
        ax.set_title('PSD')
        ax.set_xlabel('Frequency (Hz)')
        assert self.octave_spacing == 0, self.octave_spacing
        ax.set_ylabel(f'PSD (${y_units}^2$/Hz)')
        ax.plot(self.frequency, self.response[:, 0], linestyle, label=self.label[0])
        ax.legend()
        if xlim is not None:
            ax.set_xlim(xlim)
        if ylim is not None:
            ax.set_ylim(ylim)
        _set_grid(ax, xscale, yscale)
        if show:
            plt.show()

class VibrationResponseSpectra(PowerSpectralDensity):
    #def __init__(self, frequency: np.ndarray, vrs_response: np.ndarray, label: list[str],
                 #sided: int=1, is_onesided_center: bool=None, octave_spacing: int=0):
        #if vrs_response.ndim == 1:
            #psd_response = psd_response.reshape(len(psd_response), 1)
        #if 'complex' in psd_response.dtype.name:
            #raise TypeError(psd_response)
        #assert psd_response.shape[1] == 1, psd_response.shape
        #self.frequency = frequency
        #self.response = psd_response
        #self.label = label
        #self.octave_spacing = octave_spacing
        #self.sided = sided
        #self.is_onesided_center = is_onesided_center
        ##assert sided == 2
        #assert is_onesided_center is not None
        #assert sided in {1, 2}, sided
        #assert octave_spacing >= 0, octave_spacing
        #assert isinstance(frequency, np.ndarray), type(frequency)
        #assert isinstance(psd_response, np.ndarray), type(psd_response)
        #print('psd-init', self.fsampling, self.df, self.is_onesided_center)

    def plot(self, ifig: int=1,
             ax: Optional[plt.Axes]=None,
             y_units: str='g', xscale: str='log', yscale: str='log',
             xlim: Optional[tuple[float, float]]=None,
             ylim: Optional[tuple[float, float]]=None,
             linestyle='-o',
             show: bool=True):
        #self.fsampling
        #self.df
        if ax is None:
            fig = plt.figure(ifig)
            ax = fig.gca()
        ax.set_title('PSD')
        ax.set_xlabel('Frequency (Hz)')
        assert self.octave_spacing == 0, self.octave_spacing
        ax.set_ylabel(f'VRS (${y_units}^2$/Hz)')
        ax.plot(self.frequency, self.response[:, 0], linestyle, label=self.label[0])
        ax.legend()
        _set_grid(ax, xscale, yscale)
        if xlim is not None:
            ax.set_xlim(xlim)
        if ylim is not None:
            ax.set_ylim(ylim)
        if show:
            plt.show()

def fft_to_psd_df(frequency: np.ndarray, fft_response: np.ndarray) -> np.ndarray:
    df = frequency[1] - frequency[0]
    psd_response = fft_response * np.conj(fft_response) / df
    return psd_response.real

def dft_to_onesided(frequency: np.ndarray, response: np.ndarray) -> tuple[np.ndarray, np.ndarray, bool]:
    nfreq = len(frequency)
    is_onesided_center = (nfreq % 2 == 1)
    if is_onesided_center:
        # odd
        #[0, 1, 2, 3, 4]
        # center freq is 2
        ifreq = nfreq // 2 + 1
    else:
        # even
        #[0, 1, 2, 3]
        # center freq is 1.5
        ifreq = nfreq // 2
    frequency2 = frequency[:ifreq]
    response2 = response[:ifreq, :]
    assert len(frequency2) == ifreq, frequency2.shape
    return frequency, response2, is_onesided_center

def psd_to_onesided(frequency: np.ndarray, response: np.ndarray,
                    ) -> tuple[np.ndarray, np.ndarray, bool]:
    nfreq = len(frequency)
    is_onesided_center = (nfreq % 2 == 1)
    k = 2
    if is_onesided_center:
        # odd
        #[0, 1, 2, 3, 4]
        # center freq is 2
        ifreq = nfreq // 2 + 1
        response = k * response[:ifreq, :]
        response[-1, :] /= k  #  don't adjust the Nyquist frequency
    else:
        # even
        #[0, 1, 2, 3]
        # center freq is 1.5
        ifreq = nfreq // 2
        response = k * response[:ifreq, :]

    frequency2 = frequency[:ifreq]
    assert len(frequency2) == ifreq, frequency2.shape
    response[0, :] /= k  #  don't adjust the 0 frequency
    return frequency2, response, is_onesided_center

def psd_to_twosided(frequency: np.ndarray, response: np.ndarray,
                    is_onesided_center: bool, df: float) -> tuple[np.ndarray, np.ndarray]:
    assert response.shape[1] == 1, response.shape
    nfreq = len(frequency)
    #is_even = (nfreq % 2 == 0)
    k = 2
    response2 = 1 / k * np.vstack([response,
                                  np.flipud(response)])
    #  don't adjust the 0/-1 frequency
    response2[0, :] *= k
    #response2[-1, :] *= k
    if is_onesided_center:
        # odd
        #[0, 1, 2, 3, 4]
        # center freq is 2
        nfreq = len(frequency) * 2 - 1
        ifreq = nfreq // 2 + 1
        response2[-1, :] *= k  #  don't adjust the Nyquist frequency
    else:
        # even:
        #[0, 1, 2, 3]
        # center freq is 1.5
        nfreq = len(frequency) * 2
        ifreq = nfreq // 2

    frequency2 = np.arange(0, nfreq) * df
    assert len(frequency2) == nfreq, frequency2.shape
    assert response2.shape[1] == 1, response2.shape
    return frequency2, response2

def _to_twosided_fsampling(fmax: float, df: float,
                           sided: int, is_onesided_center: bool) -> float:
    if sided == 2:
        fsampling = fmax
    else:
        assert sided == 1, sided
        if is_onesided_center:
            fsampling = fmax * 2
        else:
            fsampling = fmax * 2 + df
    return fsampling

def _response_squeeze(response: np.ndarray) -> np.ndarray:
    if response.shape[1] == 1:
        response = response[:, 0]
    return response

def _onesided_frequency(dt: float, tmax: float, ntimes: int) -> np.ndarray:
    df = 1 / tmax
    #fsampling = 1 / dt
    #fnyquist = fsampling / 2
    frequency = np.arange(0, ntimes) * df
    return frequency

def _set_grid(ax: plt.Axes, xscale: str, yscale: str) -> None:
    ax.set_xscale(xscale)
    ax.set_yscale(yscale)
    if xscale == 'linear':
        ax.grid(True)
    else:
        assert xscale == 'log', xscale
        ax.grid(True, which='both')

def _adjust_axes_limit(ax2: plt.Axes, imag: np.ndarray) -> None:
    if np.allclose(imag.min(), imag.max()):
        imag_min = imag.min()
        ax2.set_ylim([imag_min - 1, imag_min + 1])

def main():
    #  [0, 1, 2, *3, 4, 5, 6]
    fsamp2 = _to_twosided_fsampling(fmax=3, df=1, sided=1, is_onesided_center=1)
    assert np.allclose(fsamp2, 6), fsamp2

    #  [0, 1, *1.5, 2, 3]
    fsamp1 = _to_twosided_fsampling(fmax=1, df=1, sided=1, is_onesided_center=0)
    assert np.allclose(fsamp1, 3), fsamp1

    A = 2.
    freq = 10  # Hz
    #nperiods = 5.
    #npoints_per_period = 1001
    df = 1
    fmax = 2000.
    dt = 1 / fmax
    #tmax = 1 / df
    nfreqs = int(fmax / df)
    ntimes = nfreqs
    #tmax = nperiods * npoints_per_period * dt
    #ntimes = int(nperiods * npoints_per_period * dt)
    #ntimes = tmax / dt

    t = np.linspace(0., ntimes, num=ntimes) * dt
    y = A * np.sin(2*np.pi*freq*t)

    time_y = TimeSeries(t, y, label=['numpy'])
    time_y2 = time_y.to_fft(sided=1, fft_type='real_imag').to_psd(sided=1).to_onesided().to_time_series()
    if 0:
        time_y.plot(ifig=1, show=False)

    #fft_y = time_y.to_fft(fft_type='mag_phase', sided=2)
    fft_y = time_y.to_fft(fft_type='real_imag', sided=2)
    if 0:
        fft_y.plot_real_imag(ifig=2, xscale='log', show=False)
        fft_y.plot_mag_phase(ifig=3, xscale='log', show=False)
    psd_fft_y0 = fft_y.to_psd(sided=2)
    psd_y1 = time_y.to_psd(sided=2)
    #psd_y.label = ['numpy']
    if 0:
        psd_y1.plot(ifig=4, yscale='linear', show=False)

    psd_y2 = time_y.to_psd_welch(sided=1, window='boxcar')
    psd_y2.label = ['welch']
    if 0:
        psd_y2.plot(ifig=4, xscale='log', yscale='linear', show=False)

    fig1 = plt.figure(5)
    ax1, ax2, ax3 = fig1.subplots(nrows=3)

    time_y_from_fft = fft_y.to_time()
    fft_y.to_onesided()
    psd_fft_y0.to_onesided()
    psd_y1.to_onesided()
    psd_y2.to_onesided()

    time_y.plot(ax=ax1, y_units='g', linestyle='-', show=False)
    time_y_from_fft.plot(ax=ax1, y_units='g', linestyle='--', show=False)
    #fft_y.plot_mag(ax=ax2, y_units='g', show=False)

    #vrs.plot(ax=ax2, y_units='g', yscale='linear', linestyle='--o', show=False)

    psd_fft_y0.plot(ax=ax3, y_units='g', yscale='linear', show=False)
    psd_y1.plot(ax=ax3, y_units='g', yscale='linear', linestyle='--o', show=False)
    psd_y2.plot(ax=ax3, y_units='g', yscale='linear', linestyle='--', show=False)

    #fft_y.to_twosided()

    psd_fft_y0.to_twosided()
    psd_y1.to_twosided()
    psd_y2.to_twosided()
    plt.close()

    frequency = np.array([20., 150., 600., 2000])
    psd_response = np.array([0.0053, 0.04, 0.04, 0.0036])
    num = 1 + 2000 // 2
    frequency2 = np.linspace(20., 2000., num=num,)
    #frequency2[0] = 1e-6
    #psd_response2 = np.interp(frequency2, frequency, psd_response)

    psd1 = PowerSpectralDensity(
        frequency, psd_response, label=['base'], sided=1,
        is_onesided_center=True, octave_spacing=0)

    psd2 = psd1.resample(frequency2, inplace=False)
    psd2.label = ['interp']
    vrs = psd2.to_vrs(Q=10)
    vrs.label = ['vrs']

    vrs2 = psd2.to_sdof_vrs_response(Q=10, fn=100)
    vrs2.label = ['vrs2']

    fig = plt.figure(10)
    #ax1 = fig.gca()
    ax1, ax2 = fig.subplots(nrows=2)
    psd1.plot(ax=ax1, y_units='g', xscale='log', yscale='log', linestyle='-', show=False)
    #psd2.plot(ax=ax1, y_units='g', xscale='log', yscale='log', linestyle='--', xlim=xlim, show=False)
    xlim = None
    vrs.plot(ax=ax2, y_units='g', xscale='log', yscale='log', linestyle='-', xlim=xlim, show=False)

    xlim = (10., 2000.)
    #vrs2.plot(ax=ax1, y_units='g', xscale='log', yscale='log', linestyle='--', xlim=xlim, show=False)

    #ax1.set_ylim([0.001, 0.1])
    ax2.set_ylim([1, 20.])
    #ax1.set_xlim([10, 2000])
    #ax2.set_xlim([10, 2000])

def plot_tf():
    fig11 = plt.figure(11)
    ax11 = fig11.gca()
    frequency = np.array([20., 2000])
    psd_response = np.array([1, 1])
    psd2 = PowerSpectralDensity(
        frequency, psd_response, label=['base'], sided=1,
        is_onesided_center=True, octave_spacing=0)
    frequency2 = np.linspace(20., 2000., num=2001-20)
    psd2.resample(frequency2, inplace=True)

    for Q in [5, 10, 25, 50]:
        tf = psd2.to_sdof_transmissibility(Q=Q, fn=100)
        tf.label = [f'Q={Q}']
        tf.frequency /= 100.
        tf.plot_mag(ax=ax11, y_units='g', xscale='log', yscale='log', linestyle='-', show=False)
    ax11.set_xlim((0.1, 10.))
    ax11.set_ylim((0.01, 100.))
    #ax11.xaxis.set_major_formatter('{:.1f} km')
    ax11.xaxis.set_major_formatter(ticker.FormatStrFormatter('%g'))
    ax11.yaxis.set_major_formatter(ticker.FormatStrFormatter('%g'))
    plt.show()

if __name__ == '__main__':
    #main()
    plot_tf()
