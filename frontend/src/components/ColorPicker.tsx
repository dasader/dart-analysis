import { TAG_COLORS } from "../types";

interface ColorPickerProps {
  value: string;
  onChange: (hex: string) => void;
  size?: "md" | "sm";
}

const swatchSize: Record<"md" | "sm", string> = {
  md: "h-7 w-7 ring-offset-2",
  sm: "h-6 w-6 ring-offset-1",
};

/** TAG_COLORS 팔레트에서 색상 하나를 고르는 스와치 그리드. */
export default function ColorPicker({ value, onChange, size = "md" }: ColorPickerProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {TAG_COLORS.map((hex) => (
        <button
          key={hex}
          type="button"
          onClick={() => onChange(hex)}
          style={{ backgroundColor: hex }}
          className={`rounded-full transition-transform hover:scale-110 ${swatchSize[size]} ${
            value === hex ? "scale-110 ring-2 ring-gray-400" : ""
          }`}
          title={hex}
        />
      ))}
    </div>
  );
}
