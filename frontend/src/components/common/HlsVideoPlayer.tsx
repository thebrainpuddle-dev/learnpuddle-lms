// src/components/common/HlsVideoPlayer.tsx

import React, { useEffect, useRef } from 'react';
import Hls from 'hls.js';

interface HlsVideoPlayerProps {
  src: string;
  className?: string;
  controls?: boolean;
  autoPlay?: boolean;
}

/**
 * Video player that automatically uses HLS.js for .m3u8 streams
 * and falls back to native <video> for regular video URLs.
 */
export const HlsVideoPlayer: React.FC<HlsVideoPlayerProps> = ({
  src,
  className = '',
  controls = true,
  autoPlay = false,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !src) return;

    const isHls = src.includes('.m3u8');

    if (isHls && Hls.isSupported()) {
      const hls = new Hls({
        maxBufferLength: 30,
        maxMaxBufferLength: 60,
      });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        if (autoPlay) video.play().catch(() => {});
      });
      return () => {
        hls.destroy();
      };
    } else if (isHls && video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari natively supports HLS
      video.src = src;
      if (autoPlay) video.play().catch(() => {});
    } else {
      // Regular video file
      video.src = src;
      if (autoPlay) video.play().catch(() => {});
    }
  }, [src, autoPlay]);

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
