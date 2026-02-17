// src/components/common/HlsVideoPlayer.tsx

import React, { useEffect, useRef, useState } from 'react';
import Hls from 'hls.js';

interface HlsVideoPlayerProps {
  src: string;
  className?: string;
  controls?: boolean;
  autoPlay?: boolean;
}

/**
 * Video player that uses HLS.js for .m3u8 streams (with auth headers)
 * and falls back to native <video> for regular video URLs.
 */
export const HlsVideoPlayer: React.FC<HlsVideoPlayerProps> = ({
  src,
  className = '',
  controls = true,
  autoPlay = false,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;
    setError(null);

    const isHls = src.includes('.m3u8');

    if (isHls && Hls.isSupported()) {
      const hls = new Hls({
        xhrSetup: (xhr) => {
          const token = sessionStorage.getItem('access_token');
          if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        },
        maxBufferLength: 30,
        maxMaxBufferLength: 60,
      });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoPlay) video.play().catch(() => {});
      });
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) {
          if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
            setError('Network error — could not load video. Please check your connection.');
          } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
            hls.recoverMediaError();
          } else {
            setError('Video playback error. Try refreshing the page.');
          }
        }
      });
      return () => {
        hls.destroy();
      };
    } else {
      // Non-HLS source (regular mp4, etc.)
      video.src = src;
      if (autoPlay) video.play().catch(() => {});
    }
  }, [src, autoPlay]);

  if (error) {
    return (
      <div className={`flex items-center justify-center bg-black text-white ${className}`}>
        <div className="text-center p-8">
          <p className="text-red-400 font-medium mb-2">Playback Error</p>
          <p className="text-sm text-gray-400">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      className={className}
      controls={controls}
      controlsList="nodownload"
      playsInline
    >
      Your browser does not support the video tag.
    </video>
  );
};
