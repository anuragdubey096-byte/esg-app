export default function SkipLink({ targetId = 'primary-content' }) {
  return (
    <a className="skip-link" href={`#${targetId}`}>
      Skip to main content
    </a>
  )
}
