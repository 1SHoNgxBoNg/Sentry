import type {mat3} from 'gl-matrix';
import {vec2} from 'gl-matrix';

import type {FlamegraphTheme} from 'sentry/utils/profiling/flamegraph/flamegraphTheme';
import {getContext} from 'sentry/utils/profiling/gl/utils';
import type {Rect} from 'sentry/utils/profiling/speedscope';

class CursorRenderer {
  canvas: HTMLCanvasElement;
  context: CanvasRenderingContext2D;

  theme: FlamegraphTheme;

  constructor(canvas: HTMLCanvasElement, theme: FlamegraphTheme) {
    this.canvas = canvas;
    this.theme = theme;
    this.context = getContext(canvas, '2d');
  }

  draw(
    configSpaceCursor: vec2,
    physicalSpace: Rect,
    configViewToPhysicalSpace: mat3
  ): void {
    const physicalSpaceCursor = vec2.transformMat3(
      vec2.create(),
      configSpaceCursor,
      configViewToPhysicalSpace
    );

    this.context.beginPath();
    this.context.moveTo(physicalSpaceCursor[0], 0);
    this.context.lineTo(physicalSpaceCursor[0], physicalSpace.height);

    this.context.moveTo(0, physicalSpaceCursor[1]);
    this.context.lineTo(physicalSpace.width, physicalSpaceCursor[1]);

    this.context.strokeStyle = this.theme.COLORS.CURSOR_CROSSHAIR;
    this.context.stroke();
  }
}

export {CursorRenderer};
