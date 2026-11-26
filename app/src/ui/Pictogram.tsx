import Svg, { Path } from 'react-native-svg';

// Filled shapes in the style of public signage on a 24 dp grid, drawn in-house to match the
// signage type (DESIGN.md section 8). Paths are the ones on the design canvas.
const paths = {
  climb: 'M3 21V17H8V13H12V9H16V5H21V21Z',
  buildings:
    'M4 3H20V21H14V17H10V21H4Z M7 6V9H10V6Z M14 6V9H17V6Z M7 11V14H10V11Z M14 11V14H17V11Z',
  ranks: 'M3 21V13H8V21Z M9.5 21V5H14.5V21Z M16 21V10H21V21Z',
  you: 'M8 3L3 6L5 11L8 9.6V21H16V9.6L19 11L21 6L16 3C15.4 4.6 13.9 5.5 12 5.5C10.1 5.5 8.6 4.6 8 3Z',
  chevron: 'M9 5.5L15.5 12L9 18.5L7.6 17.1L12.7 12L7.6 6.9Z',
  down: 'M5.5 9L12 15.5L18.5 9L17.1 7.6L12 12.7L6.9 7.6Z',
  back: 'M20 11H7.8L13.4 5.4L12 4L4 12L12 20L13.4 18.6L7.8 13H20Z',
  scan: 'M3 3H9V5H5V9H3Z M15 3H21V9H19V5H15Z M3 15H5V19H9V21H3Z M19 15H21V21H15V19H19Z M6 11H18V13H6Z',
  check: 'M9.5 16.2L5.3 12L3.9 13.4L9.5 19L20.1 8.4L18.7 7Z',
  pending: 'M6 3H18L12 12Z M12 12L18 21H6Z',
  cross:
    'M6.4 5L5 6.4L10.6 12L5 17.6L6.4 19L12 13.4L17.6 19L19 17.6L13.4 12L19 6.4L17.6 5L12 10.6Z',
  alert: 'M12 3L22 20H2Z M11 9V15H13V9Z M11 16.5V18.5H13V16.5Z',
  lock: 'M5 10H19V21H5Z M11 14V18H13V14Z M8 10V7A4 4 0 0 1 16 7V10H14V7A2 2 0 0 0 10 7V10Z',
  flag: 'M5 3H7V21H5Z M8 4H19L16.5 8L19 12H8Z',
  battery: 'M9 2H15V4H18V22H6V4H9Z M8 6V20H16V6Z M9 14H15V19H9Z',
};

export type PictogramName = keyof typeof paths;

export function Pictogram({
  name,
  size = 24,
  color,
}: {
  name: PictogramName;
  size?: number;
  color: string;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <Path d={paths[name]} fill={color} />
    </Svg>
  );
}
