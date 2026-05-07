import { useEffect, useState } from "react";
import { Image as KonvaImage } from "react-konva";

export function useHtmlImage(url: string | null): HTMLImageElement | null {
  const [img, setImg] = useState<HTMLImageElement | null>(null);

  useEffect(() => {
    if (!url) {
      setImg(null);
      return;
    }
    const i = new window.Image();
    i.crossOrigin = "anonymous";
    i.onload = () => setImg(i);
    i.onerror = () => setImg(null);
    i.src = url;
    return () => {
      i.onload = null;
      i.onerror = null;
    };
  }, [url]);

  return img;
}

/** Konva 베이스 타일 이미지 (줌/팬은 상위 Group/Stage) */
export function TileImageLayer(props: {
  image: HTMLImageElement | null;
  width: number;
  height: number;
}) {
  const { image, width, height } = props;
  if (!image) {
    return null;
  }
  return <KonvaImage image={image} width={width} height={height} listening={false} />;
}
