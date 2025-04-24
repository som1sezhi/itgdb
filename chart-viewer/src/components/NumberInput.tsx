import {
  ChangeEventHandler,
  FocusEventHandler,
  useCallback,
  useState,
  useEffect,
  KeyboardEventHandler,
  InputHTMLAttributes,
  WheelEventHandler,
} from "react";

interface NumberInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange"> {
  value: number;
  step?: number;
  min?: number;
  max?: number;
  onChange: (newVal: number) => void;
}

export function NumberInput({
  value,
  step = 1,
  min,
  max,
  onChange,
  className,
  ...props
}: NumberInputProps) {
  const [strVal, setStrVal] = useState<string>(value.toString());

  // update number display when props.value changes
  useEffect(() => {
    setStrVal(value.toString());
  }, [value]);

  const handleChange = useCallback<ChangeEventHandler<HTMLInputElement>>(
    (e) => {
      const newStrVal = e.target.value;
      setStrVal(newStrVal);
    },
    []
  );

  // normalize value on defocus
  const onBlur = useCallback<FocusEventHandler<HTMLInputElement>>(() => {
    const newVal = Number(strVal);
    if (strVal === "" || !isFinite(newVal)) {
      setStrVal(value.toString());
    } else {
      setStrVal(newVal.toString());
      onChange(newVal);
    }
  }, [strVal, value, onChange]);

  // "confirm" value by pressing enter
  const onKeyDown = useCallback<KeyboardEventHandler<HTMLInputElement>>((e) => {
    if (e.key === "Enter") {
      (e.target as HTMLInputElement).blur();
    }
  }, []);

  // scroll to change value
  const onWheel = useCallback<WheelEventHandler<HTMLInputElement>>((e) => {
    let newVal = value - Math.sign(e.deltaY) * step;
    if (typeof min === 'number')
      newVal = Math.max(min, newVal);
    setStrVal(newVal.toString());
    onChange(newVal);
  }, [min, value, step, onChange]);

  return (
    <input
      {...props}
      className={`number-input ${className ?? ""}`}
      type="text"
      inputMode="decimal"
      pattern="[0-9.]*"
      value={strVal}
      step={step}
      min={min}
      max={max}
      onChange={handleChange}
      onBlur={onBlur}
      onKeyDown={onKeyDown}
      onWheel={onWheel}
    />
  );
}
