import styles from './SegmentedControl.module.css'

export type SegmentedOption<T> = {
  value: T
  label: string
}

type Props<T> = {
  /** The radio group's name; unique per control on the page. */
  name: string
  options: SegmentedOption<T>[]
  value: T
  onChange: (value: T) => void
}

/** A segmented control built from real radio buttons, so it keeps native
 * keyboard and screen reader behavior. Put it in a fieldset with a legend. */
function SegmentedControl<T extends string | number>({
  name,
  options,
  value,
  onChange,
}: Props<T>) {
  return (
    <div className={styles.segmented}>
      {options.map((option) => (
        <label key={option.value} className={styles.segment}>
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => onChange(option.value)}
          />
          {option.label}
        </label>
      ))}
    </div>
  )
}

export default SegmentedControl
