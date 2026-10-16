package org.acestream.engine;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.locks.ReentrantLock;

import org.acestream.engine.service.v0.IAceStreamEngine;
import org.acestream.engine.service.v0.IAceStreamEngineCallback;
import org.acestream.engine.service.v0.IStartEngineResponse;

import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.ServiceConnection;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.RemoteException;
import android.util.Log;
import android.util.Pair;

public class ServiceClient {

    private final static String TAG = "AS/ServiceClient";

    private IAceStreamEngine mService = null;
    private boolean mBound = false;
    private boolean mIsActive = false;
    private boolean mStartOnBind;
    private boolean mEnableAceCastServerOnBind = false;
    private final String mName;
    private final Context mContext;
    private final Callback mCallback;
    private final ReentrantLock mBoundLock = new ReentrantLock();

    private String mAccessToken = null;
    private int mEngineApiPort = 0;
    private int mHttpApiPort = 0;

    private Handler mHandler = new Handler(Looper.getMainLooper());

    public interface Callback {
        void onConnected(IAceStreamEngine service);
        void onFailed();
        void onDisconnected();
        void onUnpacking();
        void onStarting();
        void onStopped();
        void onPlaylistUpdated();
        void onEPGUpdated();
        void onRestartPlayer();
        void onSettingsUpdated();
        void onAuthUpdated();
    }

    public static class ServiceMissingException extends Exception {}

    private IAceStreamEngineCallback mRemoteCallback = new IAceStreamEngineCallback.Stub() {
        @Override
        public void onUnpacking() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onUnpacking();
                }
            });
        }

        @Override
        public void onStopped() throws RemoteException {
            setIsActive(false);
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onStopped();
                }
            });
        }

        @Override
        public void onWaitForNetworkConnection() {
        }

        @Override
        public void onStarting() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onStarting();
                }
            });
        }

        @Override
        public void onPlaylistUpdated() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onPlaylistUpdated();
                }
            });
        }

        @Override
        public void onEPGUpdated() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onEPGUpdated();
                }
            });
        }

        @Override
        public void onAuthUpdated() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onAuthUpdated();
                }
            });
        }

        @Override
        public void onSettingsUpdated() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onSettingsUpdated();
                }
            });
        }

        @Override
        public void onRestartPlayer() throws RemoteException {
            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    mCallback.onRestartPlayer();
                }
            });
        }

        @Override
        public void onReady(int port) throws RemoteException {
            final boolean success = (port != -1);
            setIsActive(success);
            if (success) {
                mAccessToken = mService.getAccessToken();
                mEngineApiPort = mService.getEngineApiPort();
                mHttpApiPort = mService.getHttpApiPort();
            }

            runOnMainThread(new Runnable() {
                @Override
                public void run() {
                    if (success) {
                        mCallback.onConnected(mService);
                    } else {
                        mCallback.onFailed();
                    }
                }
            });
        }
    };

    private final IStartEngineResponse mStartEngineCallback = new IStartEngineResponse.Stub() {
        @Override
        public void onResult(boolean success) throws RemoteException {
            mAccessToken = mService.getAccessToken();
            mEngineApiPort = mService.getEngineApiPort();
            mHttpApiPort = mService.getHttpApiPort();
            mRemoteCallback.onReady(mEngineApiPort);
        }
    };

    private ServiceConnection mConnection = new ServiceConnection() {
        @Override
        public void onServiceDisconnected(ComponentName name) {
            mCallback.onDisconnected();
            mService = null;
            mBound = false;
        }

        @Override
        public void onServiceConnected(ComponentName name, IBinder service) {
            mService = IAceStreamEngine.Stub.asInterface(service);
            try {
                mService.registerCallbackExt(mRemoteCallback, true);
                if (mStartOnBind) {
                    mService.startEngineWithCallback(mStartEngineCallback);
                }
                if (mEnableAceCastServerOnBind) {
                    mService.enableAceCastServer();
                }
            } catch (RemoteException e) {
                Log.e(TAG, "error", e);
                mCallback.onFailed();
            }
        }
    };

    public ServiceClient(String name, Context ctx, Callback callback) {
        this(name, ctx, callback, true);
    }

    public ServiceClient(String name, Context ctx, Callback callback, boolean startOnBind) {
        mName = name;
        mContext = ctx;
        mCallback = callback;
        mStartOnBind = startOnBind;
    }

    public String getAccessToken() {
        return mAccessToken;
    }

    public int getEngineApiPort() {
        return mEngineApiPort;
    }

    public int getHttpApiPort() {
        return mHttpApiPort;
    }

    private static List<ResolveInfo> resolveIntent(Context ctx, Intent intent) {
        PackageManager pm = ctx.getPackageManager();
        List<ResolveInfo> resolveInfo = pm.queryIntentServices(intent, PackageManager.MATCH_DEFAULT_ONLY);
        if (resolveInfo == null || resolveInfo.size() == 0) {
            return null;
        }
        return resolveInfo;
    }

    public static String getServicePackage(Context ctx) throws ServiceMissingException {
        String selectedPackage = null;
        int maxVersion = -1;

        List<Pair<String, Integer>> packages = new ArrayList<>();

        List<String> knownPackages = new ArrayList<String>() {
            {
                add("org.acestream.media");
                add("org.acestream.media.atv");
                add("org.acestream.core");
                add("org.acestream.core.atv");
                add("org.acestream.core.web");
            }
        };
        for (String packageName : knownPackages) {
            int version = getAppVersion(ctx, packageName);
            if (version != -1) {
                packages.add(new Pair<>(packageName, version));
                if (version > maxVersion) {
                    maxVersion = version;
                }
            }
        }

        Intent intent = new Intent("org.acestream.engine.service.v0.IAceStreamEngine");
        List<ResolveInfo> services = resolveIntent(ctx, intent);
        if (services != null) {
            for (ResolveInfo ri : services) {
                int version = getAppVersion(ctx, ri.serviceInfo.packageName);
                if (version != -1) {
                    if (!knownPackages.contains(ri.serviceInfo.packageName)) {
                        packages.add(new Pair<>(ri.serviceInfo.packageName, version));
                        if (version > maxVersion) {
                            maxVersion = version;
                        }
                    }
                }
            }
        }

        for (Pair<String, Integer> item : packages) {
            if (item.second == maxVersion) {
                selectedPackage = item.first;
                break;
            }
        }

        if (selectedPackage == null) {
            throw new ServiceMissingException();
        }

        return selectedPackage;
    }

    private static int getAppVersion(Context ctx, String packageName) {
        int versionCode;
        try {
            PackageInfo pkgInfo = ctx.getPackageManager().getPackageInfo(packageName, 0);
            versionCode = pkgInfo.versionCode;
        } catch (PackageManager.NameNotFoundException e) {
            versionCode = -1;
        }
        return versionCode;
    }

    public static Intent getServiceIntent(Context ctx) throws ServiceMissingException {
        Intent intent = new Intent(org.acestream.engine.service.v0.IAceStreamEngine.class.getName());
        String servicePackage = getServicePackage(ctx);
        intent.setPackage(servicePackage);
        return intent;
    }

    public void bind() throws ServiceMissingException {
        mBoundLock.lock();
        try {
            if (!mBound) {
                mBound = mContext.bindService(getServiceIntent(mContext), mConnection, Context.BIND_AUTO_CREATE);
            }
        } finally {
            mBoundLock.unlock();
        }
    }

    public void unbind() {
        mBoundLock.lock();
        try {
            if (mBound) {
                if (mService != null) {
                    try {
                        mService.unregisterCallback(mRemoteCallback);
                    } catch (RemoteException e) {
                        e.printStackTrace();
                    }
                }
                mContext.unbindService(mConnection);
                mBound = false;
            }
        } finally {
            mBoundLock.unlock();
        }
    }

    public void startEngine() throws ServiceMissingException {
        if (mService != null) {
            try {
                mService.startEngineWithCallback(mStartEngineCallback);
            } catch (Throwable e) {
                Log.e(TAG, "Failed to start engine", e);
                mCallback.onFailed();
            }
        } else {
            mStartOnBind = true;
            if (!mBound) {
                bind();
            }
        }
    }

    public void enableAceCastServer() throws ServiceMissingException {
        if (mService != null) {
            try {
                mService.enableAceCastServer();
            } catch (Throwable e) {
                Log.e(TAG, "Failed to enable AceCast server", e);
            }
        } else {
            mEnableAceCastServerOnBind = true;
            if (!mBound) {
                bind();
            }
        }
    }

    synchronized void setIsActive(boolean active) {
        if (!mIsActive) {
            mIsActive = active;
        }
    }

    public synchronized boolean isActive() {
        return mIsActive;
    }

    public synchronized boolean isBound() {
        mBoundLock.lock();
        try {
            return mBound;
        } finally {
            mBoundLock.unlock();
        }
    }

    private void runOnMainThread(Runnable runnable) {
        if (Looper.myLooper() == Looper.getMainLooper()) {
            runnable.run();
        } else {
            mHandler.post(runnable);
        }
    }
}
